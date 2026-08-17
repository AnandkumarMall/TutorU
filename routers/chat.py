from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from utils import tutor_app

router = APIRouter()

@router.post("/ask_question", name="ask_question")
async def ask_question(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    question = data.get('question')
    course_name = data.get('course_name')
    chapter_title = data.get('chapter_title')
    lesson_title = data.get('lesson_title')
    
    final_state = await tutor_app.ainvoke(
        {
            "question": question,
            "course_name": course_name,
            "chapter_title": chapter_title,
            "lesson_title": lesson_title
        }
    )
    
    answer = final_state.get("answer", "")
    citation = f'\n\n<small class="text-muted"><i class="fas fa-book me-1"></i>Reference: {lesson_title}</small>'
    
    return JSONResponse({'success': True, 'answer': answer + citation, 'citation': "Formatted explanation"})
