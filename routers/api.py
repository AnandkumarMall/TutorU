import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import Course, Chapter, Lesson, Quiz
from utils import content_chain, quiz_chain
from dependencies import render_markdown

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/course_status/{course_id}")
async def course_status(course_id: int, db: AsyncSession = Depends(get_db)):
    course = await db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return JSONResponse({"is_generating": course.is_generating})

@router.post("/generate_lesson")
async def generate_lesson(data: dict, db: AsyncSession = Depends(get_db)):
    course_id = data.get("course_id")
    chapter_id = data.get("chapter_id")
    lesson_id = data.get("lesson_id")

    course = await db.get(Course, course_id)
    chapter = await db.get(Chapter, chapter_id)
    lesson = await db.get(Lesson, lesson_id)

    if not all([course, chapter, lesson]):
        raise HTTPException(status_code=404, detail="Item not found")

    if not lesson.content:
        raw_content = await content_chain.ainvoke({
            "course": course.course_name,
            "chapter": chapter.chapter_title,
            "lesson": lesson.lesson_title,
        })
        lesson.content = raw_content
        lesson.content_html = render_markdown(raw_content)
        lesson.vector_indexed = False
        await db.commit()

    return JSONResponse({
        "success": True, 
        "content_html": lesson.content_html
    })


@router.post("/generate_quiz")
async def generate_quiz(data: dict, db: AsyncSession = Depends(get_db)):
    course_id = data.get("course_id")
    chapter_id = data.get("chapter_id")
    lesson_id = data.get("lesson_id")
    quiz_type = data.get("quiz_type")
    
    today = datetime.now().strftime("%Y-%m-%d")

    course = await db.get(Course, course_id)
    chapter = await db.get(Chapter, chapter_id)

    if not all([course, chapter]):
        raise HTTPException(status_code=404, detail="Item not found")

    stmt = select(Quiz).where(
        Quiz.course_id == course_id,
        Quiz.chapter_id == chapter_id,
        Quiz.quiz_type == quiz_type,
        Quiz.date == today
    )
    if lesson_id:
        stmt = stmt.where(Quiz.lesson_id == lesson_id)

    questions = (await db.execute(stmt)).scalars().all()

    if not questions:
        lesson_title = ""
        if lesson_id:
            lesson = await db.get(Lesson, lesson_id)
            if lesson:
                lesson_title = lesson.lesson_title

        quiz_data = await quiz_chain.ainvoke({
            "course": course.course_name,
            "chapter": chapter.chapter_title,
            "lesson": lesson_title,
            "quiz_type": quiz_type,
        })

        for q in quiz_data.questions:
            quiz = Quiz(
                course_id=course.course_id,
                chapter_id=chapter_id,
                lesson_id=lesson_id,
                quiz_type=quiz_type,
                question=q.question,
                options=json.dumps(q.options),
                correct_answer=q.correct_answer,
                date=today
            )
            db.add(quiz)
            questions.append(quiz)
        
        await db.commit()

    # Return questions in JSON format to be rendered by JS
    out_questions = []
    for q in questions:
        out_questions.append({
            "question": q.question,
            "options": json.loads(q.options),
            "correct_answer": q.correct_answer
        })

    return JSONResponse({"success": True, "questions": out_questions})
