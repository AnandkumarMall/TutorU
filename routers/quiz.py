import json
from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from models import Course, Chapter, Lesson, Quiz, TodaysTask, Schedule
from dependencies import render, flash

from utils import quiz_chain

router = APIRouter()

@router.get("/quiz/{course_name}/{chapter_id}/{lesson_id}", response_class=HTMLResponse, name="quiz_view")
@router.get("/quiz/{course_name}/{chapter_id}", response_class=HTMLResponse, name="quiz_view_large")
async def quiz_view(request: Request, course_name: str, chapter_id: int, lesson_id: int = None, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.course_name == course_name).first()
    chapter = db.query(Chapter).filter(Chapter.chapter_id == chapter_id).first()
    
    quiz_type = "Short Quiz" if lesson_id else "Large Quiz"
    today = datetime.now().date().strftime("%Y-%m-%d")
    
    query = db.query(Quiz).filter(Quiz.course_id == course.course_id, Quiz.chapter_id == chapter_id, Quiz.quiz_type == quiz_type, Quiz.date == today)
    if lesson_id:
        query = query.filter(Quiz.lesson_id == lesson_id)
        lesson = db.query(Lesson).filter(Lesson.lesson_id == lesson_id).first()
        lesson_title = lesson.lesson_title if lesson else None
    else:
        lesson_title = None
        
    questions = query.all()
    
    retake = request.query_params.get('retake') == 'true'
    if questions and retake:
        for q in questions:
            db.delete(q)
        db.commit()
        questions = []
    
    if not questions:
        context = chapter.chapter_title
        if lesson_id and lesson_title:
            context += f", lesson: {lesson_title}"
            
        quiz_data = await quiz_chain.ainvoke({
            "course": course_name,
            "chapter": context,
            "quiz_type": quiz_type
        })
        
        for question in quiz_data.questions:
            quiz = Quiz(
                date=today,
                course_id=course.course_id,
                chapter_id=chapter_id,
                lesson_id=lesson_id,
                quiz_type=quiz_type,
                question=question.question,
                options=json.dumps(question.options),
                correct_answer=question.correct_answer
            )
            db.add(quiz)
        db.commit()
        questions = query.all()
        
    questions_data = []
    for q in questions:
        questions_data.append({
            'question': q.question,
            'options': json.loads(q.options),
            'correct_answer': q.correct_answer
        })
        
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
        "total": len(questions)
    })


@router.post("/submit_quiz", name="submit_quiz")
async def submit_quiz(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    course_name = data.get("course_name")
    chapter_id = data.get("chapter_id")
    lesson_id = data.get("lesson_id")
    quiz_type = data.get("quiz_type")
    answers = data.get("answers", [])
    
    today = datetime.now().date().strftime("%Y-%m-%d")
    
    query = db.query(Quiz).filter(
        Quiz.course_id == db.query(Course.course_id).filter(Course.course_name == course_name).scalar(),
        Quiz.chapter_id == chapter_id,
        Quiz.quiz_type == quiz_type,
        Quiz.date == today
    )
    if lesson_id:
        query = query.filter(Quiz.lesson_id == lesson_id)
        
    questions = query.all()
    
    score = 0
    total = len(questions)
    
    for i, q in enumerate(questions):
        if i < len(answers) and answers[i] == q.correct_answer:
            score += 1
            
    # Save score to all question rows for this quiz instance to easily retrieve it later
    for q in questions:
        q.score = score
            
    # Mark task as completed
    schedule_query = db.query(Schedule).filter(
        Schedule.course_id == db.query(Course.course_id).filter(Course.course_name == course_name).scalar(),
        Schedule.chapter_id == chapter_id,
        Schedule.task_type == quiz_type,
        Schedule.date == today
    )
    if lesson_id:
        schedule_query = schedule_query.filter(Schedule.lesson_id == lesson_id)
        
    schedule = schedule_query.first()
    
    if schedule:
        todays_task = db.query(TodaysTask).filter(TodaysTask.schedule_id == schedule.schedule_id, TodaysTask.date == today).first()
        if not todays_task:
            todays_task = TodaysTask(schedule_id=schedule.schedule_id, date=today, task_type=schedule.task_type)
            db.add(todays_task)
        todays_task.completed = True
        
    db.commit()
    
    from fastapi.responses import JSONResponse
    return JSONResponse({"success": True, "score": score, "total": total})
