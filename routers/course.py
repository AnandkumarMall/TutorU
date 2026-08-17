from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime

from database import get_db
from models import Course, Chapter, Lesson, Schedule, Quiz, TodaysTask
from dependencies import render, flash

from utils import chapter_chain, lesson_chain, generate_schedule, delete_course_from_vector_store

router = APIRouter()

def save_course_to_db(db: Session, course_name, course_description, chapters, lessons, schedule):
    course = Course(course_name=course_name, description=course_description if course_description else None)
    db.add(course)
    db.flush()
    
    chapter_objs = {}
    lesson_objs = {}
    
    for i, chapter_title in enumerate(chapters, 1):
        chapter = Chapter(
            course_id=course.course_id,
            chapter_title=chapter_title,
            chapter_order=i
        )
        db.add(chapter)
        db.flush()
        chapter_objs[chapter_title] = chapter
        
        if chapter_title in lessons:
            for j, lesson_title in enumerate(lessons[chapter_title].lessons, 1):
                lesson = Lesson(
                    chapter_id=chapter.chapter_id,
                    lesson_title=lesson_title,
                    lesson_order=j
                )
                db.add(lesson)
                db.flush()
                lesson_objs[lesson_title] = lesson
    
    today = datetime.now().date()
    for date_str, tasks in schedule.items():
        for task in tasks:
            task_type = "Lesson"
            lesson_id = None
            chapter_id = None
            
            if task.startswith("Short Quiz:"):
                task_type = "Short Quiz"
                lesson_title = task.replace("Short Quiz: ", "")
                lesson_id = lesson_objs.get(lesson_title).lesson_id if lesson_objs.get(lesson_title) else None
                chapter_id = lesson_objs.get(lesson_title).chapter_id if lesson_objs.get(lesson_title) else None
            elif task.startswith("Large Quiz:"):
                task_type = "Large Quiz"
                chapter_title = task.replace("Large Quiz: ", "")
                chapter_id = chapter_objs.get(chapter_title).chapter_id if chapter_objs.get(chapter_title) else None
            else:
                lesson_id = lesson_objs.get(task).lesson_id if lesson_objs.get(task) else None
                chapter_id = lesson_objs.get(task).chapter_id if lesson_objs.get(task) else None
            
            schedule_entry = Schedule(
                course_id=course.course_id,
                chapter_id=chapter_id,
                lesson_id=lesson_id,
                date=date_str,
                task_type=task_type,
                task_description=task
            )
            db.add(schedule_entry)
    
    db.commit()


@router.get("/new_course", response_class=HTMLResponse, name="new_course")
async def new_course(request: Request):
    step = request.session.get('step', 'input_course')
    return render(request, "new_course.html", {"step": step})


@router.post("/new_course", name="new_course_process")
async def new_course_process(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    action = form.get('action')
    
    if action == 'generate_chapters':
        course_name = form.get('course_name')
        course_description = form.get('course_description')
        
        request.session['course_name'] = course_name
        request.session['course_description'] = course_description
        
        description_text = f" focusing on {course_description}" if course_description else ""
        
        chapter_data = await chapter_chain.ainvoke({"course": course_name, "description_text": description_text})
        
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
        
        lesson_data = await lesson_chain.ainvoke({
            "course": course_name,
            "chapters": "\n".join(f"- {ch}" for ch in selected_chapters)
        })
        
        schedule_data = generate_schedule(lesson_data.course_structure)
        
        save_course_to_db(db, course_name, course_description, selected_chapters, lesson_data.course_structure, schedule_data.schedule)
        
        request.session.pop('step', None)
        request.session.pop('course_name', None)
        request.session.pop('course_description', None)
        request.session.pop('chapters', None)
        
        flash(request, 'Course created successfully!', 'success')
        return RedirectResponse(url=request.url_for('home'), status_code=303)
        
    return RedirectResponse(url=request.url_for('new_course'), status_code=303)


@router.get("/course/{course_name}", response_class=HTMLResponse, name="course_detail")
async def course_detail(request: Request, course_name: str, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.course_name == course_name).first()
    if not course:
        flash(request, f"Course '{course_name}' not found.", "error")
        return RedirectResponse(url=request.url_for('home'), status_code=303)
        
    chapters = db.query(Chapter).filter(Chapter.course_id == course.course_id).all()
    
    chapter_dict = {c.chapter_id: c for c in chapters}
    lessons = db.query(Lesson).filter(Lesson.chapter_id.in_(chapter_dict.keys())).all()
    
    for chapter in chapters:
        chapter.lessons = []
    
    for lesson in lessons:
        if lesson.chapter_id in chapter_dict:
            chapter_dict[lesson.chapter_id].lessons.append(lesson)
            
    completed_tasks = db.query(TodaysTask.schedule_id).filter(TodaysTask.completed == True).all()
    completed_schedule_ids = [t[0] for t in completed_tasks]
    
    completed_schedules = db.query(Schedule.lesson_id).filter(
        Schedule.schedule_id.in_(completed_schedule_ids), 
        Schedule.course_id == course.course_id,
        Schedule.task_type == 'Lesson'
    ).all()
    completed_lessons = set([s[0] for s in completed_schedules if s[0] is not None])
    
    quizzes = db.query(Quiz).filter(Quiz.course_id == course.course_id, Quiz.score != None).all()
    from collections import defaultdict
    lesson_qs = defaultdict(list)
    chapter_qs = defaultdict(list)
    for q in quizzes:
        if q.quiz_type == 'Short Quiz' and q.lesson_id is not None:
            lesson_qs[q.lesson_id].append(q)
        elif q.quiz_type == 'Large Quiz' and q.chapter_id is not None:
            chapter_qs[q.chapter_id].append(q)
            
    lesson_quiz_scores = {l_id: f"{qs[0].score}/{len(qs)}" for l_id, qs in lesson_qs.items()}
    chapter_quiz_scores = {c_id: f"{qs[0].score}/{len(qs)}" for c_id, qs in chapter_qs.items()}
            
    return render(request, "course_detail.html", {
        "course": course, 
        "course_name": course.course_name, 
        "chapters": chapters, 
        "lessons": {c.chapter_title: c.lessons for c in chapters},
        "completed_lessons": completed_lessons,
        "lesson_quiz_scores": lesson_quiz_scores,
        "chapter_quiz_scores": chapter_quiz_scores
    })


@router.post("/delete_course/{course_name}", name="delete_course")
async def delete_course(request: Request, course_name: str, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.course_name == course_name).first()
    if course:
        course_id = course.course_id
        delete_course_from_vector_store(course.course_name)
        db.query(TodaysTask).filter(
            TodaysTask.schedule_id.in_(
                db.query(Schedule.schedule_id).filter(Schedule.course_id == course_id)
            )
        ).delete(synchronize_session=False)
        db.query(Schedule).filter(Schedule.course_id == course_id).delete(synchronize_session=False)
        db.query(Quiz).filter(Quiz.course_id == course_id).delete(synchronize_session=False)
        db.query(Lesson).filter(
            Lesson.chapter_id.in_(
                db.query(Chapter.chapter_id).filter(Chapter.course_id == course_id)
            )
        ).delete(synchronize_session=False)
        db.query(Chapter).filter(Chapter.course_id == course_id).delete(synchronize_session=False)
        db.delete(course)
        db.commit()
        flash(request, f"Course '{course.course_name}' has been deleted.", "success")
        
    return RedirectResponse(url=request.url_for('home'), status_code=303)
