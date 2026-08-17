from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from database import get_db
from models import Course, Chapter, Lesson
from dependencies import render

from utils import content_chain, add_lesson_to_vector_store

router = APIRouter()

@router.get("/lesson/{course_name}/{chapter_id}/{lesson_id}", response_class=HTMLResponse, name="lesson_view")
async def lesson_view(request: Request, course_name: str, chapter_id: int, lesson_id: int, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.course_name == course_name).first()
    chapter = db.query(Chapter).filter(Chapter.chapter_id == chapter_id).first()
    lesson = db.query(Lesson).filter(Lesson.lesson_id == lesson_id).first()
    
    if not lesson.content:
        content_data = await content_chain.ainvoke({
            "course": course_name,
            "chapter": chapter.chapter_title,
            "lesson": lesson.lesson_title
        })
        lesson.content = content_data
        db.commit()
        from fastapi.concurrency import run_in_threadpool
        await run_in_threadpool(add_lesson_to_vector_store, course_name, chapter.chapter_title, lesson.lesson_title, content_data)

    all_lessons = db.query(Lesson).filter(Lesson.chapter_id == chapter_id).order_by(Lesson.lesson_order).all()
    prev_lesson = None
    next_lesson = None
    
    for i, l in enumerate(all_lessons):
        if l.lesson_id == lesson_id:
            if i > 0:
                prev_lesson = all_lessons[i-1]
            if i < len(all_lessons) - 1:
                next_lesson = all_lessons[i+1]
            break
            
    is_completed = False
    from models import Schedule, TodaysTask
    schedule = db.query(Schedule).filter(
        Schedule.course_id == course.course_id,
        Schedule.chapter_id == chapter.chapter_id,
        Schedule.lesson_id == lesson_id,
        Schedule.task_type == 'Lesson'
    ).first()
    
    if schedule:
        todays_task = db.query(TodaysTask).filter(TodaysTask.schedule_id == schedule.schedule_id, TodaysTask.completed == True).first()
        if todays_task:
            is_completed = True
        
    return render(request, "lesson_view.html", {
        "course_name": course_name,
        "chapter_id": chapter_id,
        "lesson_id": lesson_id,
        "chapter_title": chapter.chapter_title,
        "lesson_title": lesson.lesson_title,
        "content": lesson.content,
        "prev_lesson": prev_lesson,
        "next_lesson": next_lesson,
        "is_completed": is_completed
    })
