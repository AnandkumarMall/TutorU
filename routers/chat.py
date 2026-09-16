from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from utils import run_tutor
from routers.limiter import limiter

router = APIRouter()


@router.post("/ask_question", name="ask_question")
@limiter.limit("10/minute")  # prevent denial-of-wallet on paid Gemini endpoint (fixes SEC-3)
async def ask_question(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    question = data.get('question', '').strip()
    course_name = data.get('course_name', '')
    chapter_title = data.get('chapter_title', '')
    lesson_title = data.get('lesson_title', '')

    if not question:
        return JSONResponse({'success': False, 'error': 'Question cannot be empty.'}, status_code=400)

    # Note: 'content' sent by the frontend is intentionally ignored here.
    # RAG retrieves relevant context from ChromaDB — we do not pass raw page text
    # directly to the LLM as that would bypass the vector search and bloat the prompt.
    # (fixes FE-4 — frontend now sends no content field; removed from template too)

    answer = await run_tutor(
        question=question,
        course_name=course_name,
        chapter_title=chapter_title,
        lesson_title=lesson_title,
    )

    # Single clean citation block — previously server AND client both appended one (fixes FE-3)
    citation = f'<small class="text-muted"><i class="fas fa-book me-1"></i>Source: {lesson_title}</small>'

    return JSONResponse({'success': True, 'answer': answer, 'citation': citation})
