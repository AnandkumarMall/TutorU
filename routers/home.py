from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from datetime import datetime

from database import get_db
from models import Schedule, Course, TodaysTask
from dependencies import render

router = APIRouter()

@router.get("/", response_class=HTMLResponse, name="home")
async def home(request: Request, db: Session = Depends(get_db)):
    today = datetime.now().date().strftime("%Y-%m-%d")
    
    tasks = db.query(Schedule, Course.course_name)\
        .join(Course, Schedule.course_id == Course.course_id)\
        .outerjoin(TodaysTask, (TodaysTask.schedule_id == Schedule.schedule_id) & (TodaysTask.date == today))\
        .filter(Schedule.date == today, (TodaysTask.completed == False) | (TodaysTask.completed == None))\
        .all()
        
    tasks_by_course = {}
    for schedule, course_name in tasks:
        if course_name not in tasks_by_course:
            tasks_by_course[course_name] = []
        tasks_by_course[course_name].append({
            'schedule_id': schedule.schedule_id,
            'task_type': schedule.task_type,
            'task_description': schedule.task_description,
            'lesson_id': schedule.lesson_id,
            'chapter_id': schedule.chapter_id  
        })
    
    return render(request, "home.html", {
        "tasks_by_course": tasks_by_course, 
        "today": today
    })

from fastapi.responses import JSONResponse

@router.post("/mark_task_completed", name="mark_task_completed")
async def mark_task_completed(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    schedule_id = data.get('schedule_id')
    today = datetime.now().date().strftime("%Y-%m-%d")
    
    if not schedule_id:
        course_name = data.get("course_name")
        chapter_id = data.get("chapter_id")
        lesson_id = data.get("lesson_id")
        task_type = data.get("task_type")
        
        schedule = db.query(Schedule).filter(
            Schedule.course_id == db.query(Course.course_id).filter(Course.course_name == course_name).scalar(),
            Schedule.chapter_id == chapter_id,
            Schedule.lesson_id == lesson_id,
            Schedule.task_type == task_type
        ).first()
        
        if schedule:
            schedule_id = schedule.schedule_id
            
    if schedule_id:
        schedule = db.query(Schedule).filter(Schedule.schedule_id == schedule_id).first()
        task_type = schedule.task_type if schedule else "Lesson"
        
        todays_task = db.query(TodaysTask).filter(TodaysTask.schedule_id == schedule_id, TodaysTask.date == today).first()
        if not todays_task:
            todays_task = TodaysTask(schedule_id=schedule_id, date=today, task_type=task_type)
            db.add(todays_task)
            
        todays_task.completed = True
        db.commit()
        return JSONResponse({'success': True})
        
    return JSONResponse({'success': False, 'message': 'No scheduled task found for today'})
