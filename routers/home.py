from datetime import datetime

from fastapi import APIRouter, Request, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from database import get_db
from models import Schedule, Course, TodaysTask
from dependencies import render, get_courses_list

router = APIRouter()


@router.get("/", response_class=HTMLResponse, name="home")
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    now = datetime.now()
    today = now.date().strftime("%Y-%m-%d")

    # One query: join Schedule → Course, outer-join TodaysTask (for today only)
    stmt = (
        select(Schedule, Course.course_name)
        .join(Course, Schedule.course_id == Course.course_id)
        .outerjoin(
            TodaysTask,
            and_(
                TodaysTask.schedule_id == Schedule.schedule_id,
                TodaysTask.date == today,
            )
        )
        .where(
            Schedule.date == today,
            or_(TodaysTask.completed == False, TodaysTask.completed == None),
        )
    )
    rows = (await db.execute(stmt)).all()

    tasks_by_course: dict[str, list] = {}
    for schedule, course_name in rows:
        tasks_by_course.setdefault(course_name, []).append({
            'schedule_id': schedule.schedule_id,
            'task_type': schedule.task_type,
            'task_description': schedule.task_description,
            'lesson_id': schedule.lesson_id,
            'chapter_id': schedule.chapter_id,
        })

    courses = await get_courses_list(db)
    active_course_name = next(iter(tasks_by_course), None)
    active_course = next(
        (course for course in courses if course["name"] == active_course_name),
        courses[0] if courses else None,
    )

    return render(request, "home.html", {
        "tasks_by_course": tasks_by_course,
        "today": today,
        "today_label": f"{now.strftime('%A, %B')} {now.day}",
        "course_names": courses,
        "active_course": active_course,
    })


@router.post("/mark_task_completed", name="mark_task_completed")
async def mark_task_completed(request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    schedule_id = data.get('schedule_id')
    today = datetime.now().date().strftime("%Y-%m-%d")

    if not schedule_id:
        course_name = data.get("course_name")
        chapter_id = data.get("chapter_id")
        lesson_id = data.get("lesson_id")
        task_type = data.get("task_type")

        course_id = (await db.execute(
            select(Course.course_id).where(Course.course_name == course_name)
        )).scalar()

        if course_id:
            schedule = (await db.execute(
                select(Schedule).where(
                    Schedule.course_id == course_id,
                    Schedule.chapter_id == chapter_id,
                    Schedule.lesson_id == lesson_id,
                    Schedule.task_type == task_type,
                )
            )).scalars().first()
            if schedule:
                schedule_id = schedule.schedule_id

    if schedule_id:
        schedule = (await db.execute(
            select(Schedule).where(Schedule.schedule_id == schedule_id)
        )).scalars().first()
        task_type = schedule.task_type if schedule else "Lesson"

        todays_task = (await db.execute(
            select(TodaysTask).where(
                TodaysTask.schedule_id == schedule_id,
                TodaysTask.date == today,
            )
        )).scalars().first()

        try:
            schedule = (await db.execute(
                select(Schedule).where(Schedule.schedule_id == schedule_id)
            )).scalars().first()
            task_type = schedule.task_type if schedule else "Lesson"

            todays_task = (await db.execute(
                select(TodaysTask).where(
                    TodaysTask.schedule_id == schedule_id,
                    TodaysTask.date == today,
                )
            )).scalars().first()

            if not todays_task:
                todays_task = TodaysTask(schedule_id=schedule_id, date=today, task_type=task_type)
                db.add(todays_task)

            todays_task.completed = True
            await db.commit()

            # JIT pre-generate the next task in the background
            if schedule:
                from bg_tasks import _generate_task_bg
                background_tasks.add_task(_generate_task_bg, schedule.course_id)

            return JSONResponse({"success": True})
        except Exception as e:
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    return JSONResponse({'success': False, 'message': 'No scheduled task found for today'})
