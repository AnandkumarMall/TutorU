from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Request, Depends, BackgroundTasks
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from database import get_db
from models import Course, Chapter, Lesson, Schedule, Quiz, TodaysTask
from dependencies import render, flash, get_courses_list

from utils import chapter_chain, lesson_chain, generate_schedule, delete_course_from_vector_store
from routers.limiter import limiter

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def save_course_base_to_db(
    db: AsyncSession,
    course_name: str,
    course_description: str,
    chapters: list,
) -> tuple[int, dict[str, int]]:
    """
    Saves the course and chapter skeletons immediately.
    Returns (course_id, {chapter_title: chapter_id})
    """
    course = Course(
        course_name=course_name,
        description=course_description if course_description else None,
        is_generating=True,
    )
    db.add(course)
    await db.flush()
    course_id = course.course_id

    chapter_map = {}
    for i, chapter_title in enumerate(chapters, 1):
        chapter = Chapter(
            course_id=course_id,
            chapter_title=chapter_title,
            chapter_order=i,
        )
        db.add(chapter)
        await db.flush()
        chapter_map[chapter_title] = chapter.chapter_id

    await db.commit()
    return course_id, chapter_map


async def _generate_lessons_and_schedule_bg(
    course_id: int,
    course_name: str,
    selected_chapters: list[str],
    chapter_map: dict[str, int],
):
    """Background task to call Gemini and save lessons/schedule."""
    from database import AsyncSessionLocal
    import logging

    try:
        lesson_data = await lesson_chain.ainvoke({
            "course": course_name,
            "chapters": "\n".join(f"- {ch}" for ch in selected_chapters),
        })
        schedule_data = generate_schedule(lesson_data.course_structure)
        
        async with AsyncSessionLocal() as db:
            lessons = lesson_data.course_structure
            schedule = schedule_data.schedule
            lesson_objs: dict[str, tuple[int, int]] = {}
            
            for chapter_title, chapter_id in chapter_map.items():
                for j, lesson_title in enumerate(lessons.get(chapter_title, type('', (), {'lessons': []})()).lessons, 1):
                    lesson = Lesson(
                        chapter_id=chapter_id,
                        lesson_title=lesson_title,
                        lesson_order=j,
                    )
                    db.add(lesson)
                    await db.flush()
                    lesson_objs[lesson_title] = (lesson.lesson_id, chapter_id)

            for date_str, tasks in schedule.items():
                for task in tasks:
                    task_type = "Lesson"
                    lesson_id = None
                    chapter_id = None

                    if task.startswith("Short Quiz:"):
                        task_type = "Short Quiz"
                        lesson_title = task.replace("Short Quiz: ", "")
                        if lesson_title in lesson_objs:
                            lesson_id, chapter_id = lesson_objs[lesson_title]
                    elif task.startswith("Large Quiz:"):
                        task_type = "Large Quiz"
                        chapter_title_key = task.replace("Large Quiz: ", "")
                        chapter_id = chapter_map.get(chapter_title_key)
                    else:
                        if task in lesson_objs:
                            lesson_id, chapter_id = lesson_objs[task]

                    db.add(Schedule(
                        course_id=course_id,
                        chapter_id=chapter_id,
                        lesson_id=lesson_id,
                        date=date_str,
                        task_type=task_type,
                        task_description=task,
                    ))

            course = await db.get(Course, course_id)
            if course:
                course.is_generating = False
            await db.commit()

        # JIT Pre-generate the first lesson
        from bg_tasks import _generate_task_bg
        await _generate_task_bg(course_id)

    except Exception as e:
        logging.error(f"Background course generation failed: {e}")
        async with AsyncSessionLocal() as db:
            course = await db.get(Course, course_id)
            if course:
                course.is_generating = False
                await db.commit()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/new_course", response_class=HTMLResponse, name="new_course")
async def new_course(request: Request, db: AsyncSession = Depends(get_db)):
    step = request.session.get('step', 'input_course')
    return render(request, "new_course.html", {
        "step": step,
        "course_names": await get_courses_list(db),
    })


@router.post("/new_course", name="new_course_process")
@limiter.limit("5/minute")
async def new_course_process(request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    action = form.get('action')

    if action == 'generate_chapters':
        course_name = form.get('course_name', '').strip()
        course_description = form.get('course_description', '').strip()

        if not course_name:
            flash(request, 'Course name is required.', 'error')
            return RedirectResponse(url=request.url_for('new_course'), status_code=303)

        # Duplicate check BEFORE LLM call (fixes AI-5)
        existing = (await db.execute(
            select(Course).where(Course.course_name == course_name)
        )).scalars().first()
        if existing:
            flash(request, f"A course named '{course_name}' already exists.", 'error')
            return RedirectResponse(url=request.url_for('new_course'), status_code=303)

        request.session['course_name'] = course_name
        request.session['course_description'] = course_description
        description_text = f" focusing on {course_description}" if course_description else ""

        try:
            chapter_data = await chapter_chain.ainvoke({
                "course": course_name,
                "description_text": description_text,
            })
        except Exception:
            request.session.pop('course_name', None)
            request.session.pop('course_description', None)
            flash(request, 'Failed to generate chapters. Please try again.', 'error')
            return RedirectResponse(url=request.url_for('new_course'), status_code=303)

        request.session['chapters'] = chapter_data.chapters
        request.session['step'] = 'select_chapters'
        return RedirectResponse(url=request.url_for('new_course'), status_code=303)

    elif action == 'create_course':
        selected_chapters = form.getlist('selected_chapters')

        if not selected_chapters:
            flash(request, 'Please select at least one chapter.', 'error')
            return RedirectResponse(url=request.url_for('new_course'), status_code=303)

        course_name = request.session.get('course_name')
        course_description = request.session.get('course_description')

        # 1. Save course & chapters skeleton immediately
        course_id, chapter_map = await save_course_base_to_db(
            db, course_name, course_description, selected_chapters
        )

        # 2. Queue background task for lessons & schedule
        background_tasks.add_task(
            _generate_lessons_and_schedule_bg,
            course_id, course_name, selected_chapters, chapter_map
        )

        # 3. Clean up session and redirect instantly
        request.session.pop('step', None)
        request.session.pop('course_name', None)
        request.session.pop('course_description', None)
        request.session.pop('chapters', None)

        flash(request, 'Course creation started! Your lessons are being generated in the background.', 'success')
        return RedirectResponse(url=request.url_for('home'), status_code=303)

    return RedirectResponse(url=request.url_for('new_course'), status_code=303)


@router.get("/course/{course_name}", response_class=HTMLResponse, name="course_detail")
async def course_detail(request: Request, course_name: str, db: AsyncSession = Depends(get_db)):
    course = (await db.execute(
        select(Course).where(Course.course_name == course_name)
    )).scalars().first()
    if not course:
        raise HTTPException(status_code=404, detail=f"Course '{course_name}' not found.")

    chapters = (await db.execute(
        select(Chapter).where(Chapter.course_id == course.course_id).order_by(Chapter.chapter_order)
    )).scalars().all()

    chapter_ids = [c.chapter_id for c in chapters]
    lessons_all = (await db.execute(
        select(Lesson).where(Lesson.chapter_id.in_(chapter_ids)).order_by(Lesson.lesson_order)
    )).scalars().all()

    chapter_map = {c.chapter_id: c for c in chapters}
    lessons_by_chapter: dict[str, list] = {c.chapter_title: [] for c in chapters}
    for lesson in lessons_all:
        chapter = chapter_map.get(lesson.chapter_id)
        if chapter:
            lessons_by_chapter[chapter.chapter_title].append(lesson)

    # Completed lesson IDs — single JOIN subquery (fixes PERF-3)
    from sqlalchemy import exists
    completed_stmt = (
        select(Schedule.lesson_id)
        .join(TodaysTask, TodaysTask.schedule_id == Schedule.schedule_id)
        .where(
            Schedule.course_id == course.course_id,
            Schedule.task_type == 'Lesson',
            TodaysTask.completed == True,
            Schedule.lesson_id.isnot(None),
        )
    )
    completed_lessons = set(
        row[0] for row in (await db.execute(completed_stmt)).all()
    )

    quizzes = (await db.execute(
        select(Quiz).where(Quiz.course_id == course.course_id, Quiz.score.isnot(None))
    )).scalars().all()

    lesson_qs: dict[int, list] = defaultdict(list)
    chapter_qs: dict[int, list] = defaultdict(list)
    for q in quizzes:
        if q.quiz_type == 'Short Quiz' and q.lesson_id is not None:
            lesson_qs[q.lesson_id].append(q)
        elif q.quiz_type == 'Large Quiz' and q.chapter_id is not None:
            chapter_qs[q.chapter_id].append(q)

    lesson_quiz_scores = {lid: f"{qs[0].score}/{len(qs)}" for lid, qs in lesson_qs.items()}
    chapter_quiz_scores = {cid: f"{qs[0].score}/{len(qs)}" for cid, qs in chapter_qs.items()}

    return render(request, "course_detail.html", {
        "course": course,
        "course_name": course.course_name,
        "chapters": chapters,
        "lessons": lessons_by_chapter,
        "completed_lessons": completed_lessons,
        "lesson_quiz_scores": lesson_quiz_scores,
        "chapter_quiz_scores": chapter_quiz_scores,
        "course_names": await get_courses_list(db),
    })


@router.post("/delete_course/{course_name}", name="delete_course")
async def delete_course(request: Request, course_name: str, db: AsyncSession = Depends(get_db)):
    course = (await db.execute(
        select(Course).where(Course.course_name == course_name)
    )).scalars().first()

    if course:
        course_id = course.course_id
        delete_course_from_vector_store(course.course_name)

        chapter_ids_stmt = select(Chapter.chapter_id).where(Chapter.course_id == course_id)
        schedule_ids_stmt = select(Schedule.schedule_id).where(Schedule.course_id == course_id)
        lesson_ids_stmt = select(Lesson.lesson_id).where(
            Lesson.chapter_id.in_(chapter_ids_stmt)
        )

        await db.execute(delete(TodaysTask).where(TodaysTask.schedule_id.in_(schedule_ids_stmt)))
        await db.execute(delete(Quiz).where(Quiz.lesson_id.in_(lesson_ids_stmt)))
        await db.execute(delete(Schedule).where(Schedule.course_id == course_id))
        await db.execute(delete(Lesson).where(Lesson.chapter_id.in_(chapter_ids_stmt)))
        await db.execute(delete(Chapter).where(Chapter.course_id == course_id))
        await db.execute(delete(Course).where(Course.course_id == course_id))
        await db.commit()

        flash(request, f"Course '{course_name}' has been deleted.", "success")

    return RedirectResponse(url=request.url_for('home'), status_code=303)
