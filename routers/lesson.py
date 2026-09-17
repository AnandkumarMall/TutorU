from fastapi import APIRouter, Request, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import Course, Chapter, Lesson, Schedule, TodaysTask
from dependencies import render, get_courses_list, render_markdown

from utils import content_chain, add_lesson_to_vector_store

router = APIRouter()


@router.get("/lesson/{course_name}/{chapter_id}/{lesson_id}", response_class=HTMLResponse, name="lesson_view")
async def lesson_view(
    request: Request,
    course_name: str,
    chapter_id: int,
    lesson_id: int,
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

    lesson = (await db.execute(
        select(Lesson).where(Lesson.lesson_id == lesson_id)
    )).scalars().first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found.")

    # -----------------------------------------------------------------------
    # Content generation + HTML pre-rendering (PERF-8)
    # -----------------------------------------------------------------------
    needs_generation = False

    if not lesson.content:
        # Pass to template to fetch via AJAX API
        needs_generation = True

    else:
        # Content exists — handle any out-of-sync states lazily
        needs_commit = False

        if not lesson.content_html:
            # Content was generated before the content_html column was added (lazy migration)
            lesson.content_html = render_markdown(lesson.content)
            needs_commit = True

        if not lesson.vector_indexed:
            # ChromaDB and DB diverged — re-index without regenerating (AI-4)
            indexed_ok = await run_in_threadpool(
                add_lesson_to_vector_store,
                course_name, chapter.chapter_title, lesson.lesson_title, lesson.content,
            )
            if indexed_ok:
                lesson.vector_indexed = True
                needs_commit = True

        if needs_commit:
            await db.commit()

    # -----------------------------------------------------------------------
    # Navigation: prev/next lessons in the same chapter
    # -----------------------------------------------------------------------
    all_lessons = (await db.execute(
        select(Lesson)
        .where(Lesson.chapter_id == chapter_id)
        .order_by(Lesson.lesson_order)
    )).scalars().all()

    prev_lesson = next_lesson = None
    for i, l in enumerate(all_lessons):
        if l.lesson_id == lesson_id:
            if i > 0:
                prev_lesson = all_lessons[i - 1]
            if i < len(all_lessons) - 1:
                next_lesson = all_lessons[i + 1]
            break

    # -----------------------------------------------------------------------
    # All lessons in chapter (for TOC sidebar) + completion set
    # -----------------------------------------------------------------------
    from sqlalchemy import and_
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
    completed_lessons = set((await db.execute(completed_stmt)).scalars().all())
    is_completed = lesson_id in completed_lessons

    # Count all lessons in this course for progress display
    from models import Chapter as ChapterModel
    all_chapter_ids = (await db.execute(
        select(ChapterModel.chapter_id).where(ChapterModel.course_id == course.course_id)
    )).scalars().all()
    total_lessons_count = len((await db.execute(
        select(Lesson.lesson_id).where(Lesson.chapter_id.in_(all_chapter_ids))
    )).scalars().all())

    return render(request, "lesson_view.html", {
        "course_name": course_name,
        "chapter_id": chapter_id,
        "lesson_id": lesson_id,
        "chapter_title": chapter.chapter_title,
        "lesson_title": lesson.lesson_title,
        # Serve pre-rendered HTML directly — no per-request markdown parsing (PERF-8)
        "content_html": lesson.content_html,
        # Keep raw content available for the Jinja markdown filter fallback
        "content": lesson.content,
        "prev_lesson": prev_lesson,
        "next_lesson": next_lesson,
        "is_completed": is_completed,
        "course_names": await get_courses_list(db),
        "needs_generation": needs_generation,
        "course_id": course.course_id,
        # New: TOC sidebar
        "all_chapter_lessons": all_lessons,
        "completed_lessons": completed_lessons,
        "completed_lesson_count": len(completed_lessons),
        "total_lessons": total_lessons_count,
    })

