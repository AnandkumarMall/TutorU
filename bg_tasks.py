import asyncio
import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal
from models import Course, Chapter, Lesson, Schedule, Quiz, TodaysTask
from utils import content_chain, quiz_chain


async def _generate_task_bg(course_id: int):
    """
    Finds the first chronological incomplete task for the given course
    that hasn't been generated yet, and generates it in the background.
    """
    today = datetime.now().strftime('%Y-%m-%d')
    try:
        async with AsyncSessionLocal() as db:
            # Find all schedules for this course, ordered by date and ID
            schedules = (await db.execute(
                select(Schedule).where(Schedule.course_id == course_id).order_by(Schedule.date, Schedule.schedule_id)
            )).scalars().all()

            if not schedules:
                return

            for schedule in schedules:
                # Check if this schedule item is already completed today
                todays_task = (await db.execute(
                    select(TodaysTask).where(
                        TodaysTask.schedule_id == schedule.schedule_id,
                        TodaysTask.date == today,
                    )
                )).scalars().first()

                if todays_task and todays_task.completed:
                    continue  # Already completed, move to next

                # This is the next chronological task. Check if it needs generation.
                if schedule.task_type == "Lesson":
                    if not schedule.lesson_id:
                        continue
                    lesson = await db.get(Lesson, schedule.lesson_id)
                    if lesson and not lesson.content:
                        # Needs generation!
                        course = await db.get(Course, course_id)
                        chapter = await db.get(Chapter, schedule.chapter_id)
                        
                        raw_content = await content_chain.ainvoke({
                            "course": course.course_name,
                            "chapter": chapter.chapter_title,
                            "lesson": lesson.lesson_title,
                        })
                        lesson.content = raw_content
                        # We don't render markdown or index Chroma in the background task
                        # to save CPU/Memory. We'll let the AJAX endpoint or first load do it.
                        await db.commit()
                        return # Only generate one at a time

                elif schedule.task_type in ["Short Quiz", "Large Quiz"]:
                    # Check if questions exist
                    stmt = select(Quiz).where(
                        Quiz.course_id == course_id,
                        Quiz.chapter_id == schedule.chapter_id,
                        Quiz.quiz_type == schedule.task_type,
                        Quiz.date == today, # Quizzes are generated for 'today'
                    )
                    if schedule.lesson_id:
                        stmt = stmt.where(Quiz.lesson_id == schedule.lesson_id)
                    
                    questions = (await db.execute(stmt)).scalars().all()
                    
                    if not questions:
                        # Needs generation!
                        course = await db.get(Course, course_id)
                        chapter = await db.get(Chapter, schedule.chapter_id)
                        
                        chapter_title = chapter.chapter_title if chapter else ""
                        lesson_title = ""
                        
                        if schedule.lesson_id:
                            lesson = await db.get(Lesson, schedule.lesson_id)
                            if lesson:
                                lesson_title = lesson.lesson_title

                        quiz_data = await quiz_chain.ainvoke({
                            "course": course.course_name,
                            "chapter": chapter_title,
                            "lesson": lesson_title,
                            "quiz_type": schedule.task_type,
                        })

                        for q in quiz_data.questions:
                            db.add(Quiz(
                                course_id=course.course_id,
                                chapter_id=schedule.chapter_id,
                                lesson_id=schedule.lesson_id,
                                quiz_type=schedule.task_type,
                                question=q.question,
                                options=json.dumps(q.options),
                                correct_answer=q.correct_answer,
                                date=today
                            ))
                        await db.commit()
                        return # Generated one

    except Exception as e:
        logging.error(f"JIT Background generation failed: {e}")
