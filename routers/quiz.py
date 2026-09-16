import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Request, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from database import get_db
from models import Course, Chapter, Lesson, Quiz, TodaysTask, Schedule
from dependencies import render, get_course_names

from utils import quiz_chain
from routers.limiter import limiter

router = APIRouter()

# ---------------------------------------------------------------------------
# Quiz generation idempotency lock (fixes AI-6)
#
# A single-process FastAPI app shares one event loop. This dict of asyncio
# Locks ensures that two concurrent requests for the same quiz (same course /
# chapter / lesson / type / date) cannot both pass the "no questions yet"
# check and both call the LLM — which would produce duplicate rows and charge
# the Gemini API twice.
#
# The lock is released after the first request completes, so the second
# request simply finds the questions in the DB and returns them.
# ---------------------------------------------------------------------------

_quiz_locks_guard = asyncio.Lock()
_quiz_locks: dict[str, asyncio.Lock] = {}


async def _get_quiz_lock(key: str) -> asyncio.Lock:
    async with _quiz_locks_guard:
        if key not in _quiz_locks:
            _quiz_locks[key] = asyncio.Lock()
        return _quiz_locks[key]


def _build_quiz_stmt(course_id: int, chapter_id: int, lesson_id: int | None, quiz_type: str, today: str):
    """Build the SQLAlchemy select statement for fetching quiz questions."""
    stmt = select(Quiz).where(
        Quiz.course_id == course_id,
        Quiz.chapter_id == chapter_id,
        Quiz.quiz_type == quiz_type,
        Quiz.date == today,
    )
    if lesson_id is not None:
        stmt = stmt.where(Quiz.lesson_id == lesson_id)
    return stmt


@router.get("/quiz/{course_name}/{chapter_id}/{lesson_id}", response_class=HTMLResponse, name="quiz_view")
@router.get("/quiz/{course_name}/{chapter_id}", response_class=HTMLResponse, name="quiz_view_large")
@limiter.limit("10/minute")
async def quiz_view(
    request: Request,
    course_name: str,
    chapter_id: int,
    lesson_id: int = None,
    db: AsyncSession = Depends(get_db),
):
    # 404 guards (REL-1)
    course = (await db.execute(
        select(Course).where(Course.course_name == course_name)
    )).scalars().first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    chapter = (await db.execute(
        select(Chapter).where(Chapter.chapter_id == chapter_id)
    )).scalars().first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found.")

    quiz_type = "Short Quiz" if lesson_id else "Large Quiz"
    today = datetime.now().date().strftime("%Y-%m-%d")

    lesson_title: str | None = None
    if lesson_id:
        lesson = (await db.execute(
            select(Lesson).where(Lesson.lesson_id == lesson_id)
        )).scalars().first()
        lesson_title = lesson.lesson_title if lesson else None

    stmt = _build_quiz_stmt(course.course_id, chapter_id, lesson_id, quiz_type, today)

    retake = request.query_params.get('retake') == 'true'
    if retake:
        existing = (await db.execute(stmt)).scalars().all()
        if existing:
            for q in existing:
                await db.delete(q)
            await db.commit()

    questions = (await db.execute(stmt)).scalars().all()

    if not questions:
        # Acquire a per-quiz lock to prevent concurrent generation (AI-6)
        lock_key = f"{course.course_id}:{chapter_id}:{lesson_id}:{quiz_type}:{today}"
        lock = await _get_quiz_lock(lock_key)

        async with lock:
            # Double-checked locking: re-query while holding the lock
            questions = (await db.execute(stmt)).scalars().all()

            if not questions:
                context = chapter.chapter_title
                if lesson_id and lesson_title:
                    context += f", lesson: {lesson_title}"

                quiz_data = await quiz_chain.ainvoke({
                    "course": course_name,
                    "chapter": context,
                    "quiz_type": quiz_type,
                })

                for question in quiz_data.questions:
                    db.add(Quiz(
                        date=today,
                        course_id=course.course_id,
                        chapter_id=chapter_id,
                        lesson_id=lesson_id,
                        quiz_type=quiz_type,
                        question=question.question,
                        options=json.dumps(question.options),
                        correct_answer=question.correct_answer,
                    ))
                await db.commit()
                questions = (await db.execute(stmt)).scalars().all()

    questions_data = [
        {
            'question': q.question,
            'options': json.loads(q.options),
            'correct_answer': q.correct_answer,
        }
        for q in questions
    ]

    score = questions[0].score if questions and questions[0].score is not None else None

    return render(request, "quiz_view.html", {
        "course_name": course_name,
        "chapter_id": chapter_id,
        "lesson_id": lesson_id,
        "chapter_title": chapter.chapter_title,
        "lesson_title": lesson_title,
        "quiz_type": quiz_type,
        "questions": questions_data,
        "score": score,
        "total": len(questions),
        "course_names": await get_course_names(db),
    })


@router.post("/submit_quiz", name="submit_quiz")
async def submit_quiz(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    course_name = data.get("course_name")
    chapter_id = data.get("chapter_id")
    lesson_id = data.get("lesson_id")
    quiz_type = data.get("quiz_type")
    answers = data.get("answers", [])
    today = datetime.now().date().strftime("%Y-%m-%d")

    # course_id looked up once and reused (PERF-4)
    course_id = (await db.execute(
        select(Course.course_id).where(Course.course_name == course_name)
    )).scalar()
    if not course_id:
        return JSONResponse({"success": False, "message": "Course not found."}, status_code=404)

    stmt = _build_quiz_stmt(course_id, chapter_id, lesson_id, quiz_type, today)
    questions = (await db.execute(stmt)).scalars().all()

    score = sum(
        1 for i, q in enumerate(questions)
        if i < len(answers) and answers[i] == q.correct_answer
    )

    for q in questions:
        q.score = score

    # Mark schedule task completed
    sched_stmt = select(Schedule).where(
        Schedule.course_id == course_id,
        Schedule.chapter_id == chapter_id,
        Schedule.task_type == quiz_type,
        Schedule.date == today,
    )
    if lesson_id:
        sched_stmt = sched_stmt.where(Schedule.lesson_id == lesson_id)
    schedule = (await db.execute(sched_stmt)).scalars().first()

    if schedule:
        todays_task = (await db.execute(
            select(TodaysTask).where(
                TodaysTask.schedule_id == schedule.schedule_id,
                TodaysTask.date == today,
            )
        )).scalars().first()
        if not todays_task:
            todays_task = TodaysTask(
                schedule_id=schedule.schedule_id,
                date=today,
                task_type=schedule.task_type,
            )
            db.add(todays_task)
        todays_task.completed = True

    await db.commit()
    return JSONResponse({"success": True, "score": score, "total": len(questions)})
