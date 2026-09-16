import os
from typing import List, Dict
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from datetime import datetime, timedelta
import json
import logging
from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import TypedDict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ChapterSchema(BaseModel):
    chapters: List[str] = Field(description="List of 5 chapter titles")

class LessonSchema(BaseModel):
    lessons: List[str] = Field(description="List of lesson titles")

class DictionarySchema(BaseModel):
    course_structure: Dict[str, LessonSchema] = Field(description="Dictionary with chapters as keys and lesson lists as values")

class ScheduleSchema(BaseModel):
    schedule: Dict[str, List[str]] = Field(description="Dictionary with dates (YYYY-MM-DD) as keys and lists of lesson or quiz titles as values")

class LessonContentSchema(BaseModel):
    content: str = Field(description="Detailed content for the specified lesson")

class QuizQuestion(BaseModel):
    question: str = Field(description="A single quiz question")
    options: List[str] = Field(description="List of 4 answer options", min_length=4, max_length=4)
    correct_answer: str = Field(description="The correct answer")

class QuizSchema(BaseModel):
    questions: List[QuizQuestion] = Field(description="List of quiz questions")

# ---------------------------------------------------------------------------
# LLM chains (defined once at module level — not rebuilt per request)
# ---------------------------------------------------------------------------

chapter_prompt = ChatPromptTemplate.from_template(
    "Generate a list of 5 chapter titles for a course on {course}{description_text} that help in fully understanding the topic. "
    "Return a JSON object with a 'chapters' key containing the list of titles."
)
chapter_chain = chapter_prompt | llm.with_structured_output(ChapterSchema)

dictionary_parser = PydanticOutputParser(pydantic_object=DictionarySchema)
lesson_prompt = ChatPromptTemplate.from_template(
    """For a course on {course}, generate a list of 3 lessons for each chapter in the list below.

Chapters:
{chapters}

Return a JSON object that matches this format exactly:

{format_instructions}
"""
)
lesson_chain = lesson_prompt.partial(format_instructions=dictionary_parser.get_format_instructions()) | llm | dictionary_parser

content_prompt = ChatPromptTemplate.from_template(
    """Generate detailed content for a lesson in a course. The course is "{course}", the chapter is "{chapter}", and the lesson is "{lesson}". Provide a comprehensive explanation suitable for a beginner, including key concepts, examples, and practical applications. Format the content in markdown with clear headings (##), paragraphs, lists, and code blocks where appropriate.
    
    IMPORTANT: Respond with ONLY pure markdown. Do not wrap it in JSON."""
)
content_chain = content_prompt | llm | StrOutputParser()

quiz_prompt = ChatPromptTemplate.from_template(
    """Generate a {quiz_type} for a course on {course}. The context is "{chapter}".
    A Short Quiz should have 5 questions, and a Large Quiz should have 10 questions.
    Each question should have exactly 4 answer options and one correct answer.
    Provide beginner-friendly questions with clear explanations.
    Return a JSON object with a 'questions' key containing a list of questions, each with 'question', 'options', and 'correct_answer'."""
)
quiz_chain = quiz_prompt | llm | PydanticOutputParser(pydantic_object=QuizSchema)

rag_prompt = ChatPromptTemplate.from_template(
    """You are a helpful tutor explaining concepts clearly and concisely.

STUDENT QUESTION: "{question}"

LESSON CONTEXT:
Course: {course_name}
Chapter: {chapter_title} 
Lesson: {lesson_title}

RELEVANT CONTENT:
{context}

RESPONSE GUIDELINES:
- **Length**: Match the complexity of the question
  * Simple questions (what is X?): 1-2 paragraphs
  * Medium questions (how does X work?): 2-3 paragraphs  
  * Complex questions (explain X in detail): 3-4 paragraphs
- **Format**: Use clear headings, bullet points, and emphasis
- **Style**: Conversational but professional
- **Focus**: Explain concepts clearly with 1-2 good examples

IMPORTANT: Use **bold** for key terms and *italics* for emphasis. Structure your answer with clear sections.

Your explanation:"""
)

# Module-level chain — not rebuilt on every request (was bug AI-7)
rag_chain = rag_prompt | llm | StrOutputParser()

# ---------------------------------------------------------------------------
# Schedule generation (pure Python, no LLM)
# ---------------------------------------------------------------------------

def generate_schedule(lessons: Dict[str, LessonSchema]) -> ScheduleSchema:
    schedule = {}
    current_date = datetime.now().date()
    day_offset = 0

    for chapter, lesson_schema in lessons.items():
        for lesson in lesson_schema.lessons:
            date_str = (current_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
            schedule[date_str] = [lesson, f"Short Quiz: {lesson}"]
            day_offset += 1
        date_str = (current_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        schedule[date_str] = [f"Large Quiz: {chapter}"]
        day_offset += 1

    return ScheduleSchema(schedule=schedule)

# ---------------------------------------------------------------------------
# ChromaDB / RAG — lazy-initialized via startup event (fixes AI-9 / PERF-9)
# ---------------------------------------------------------------------------

CHROMA_PERSIST_DIR = os.path.join("instance", "chroma_db")

# These are populated by init_vector_store(), called from app startup.
global_embedder = None
global_chroma = None

def init_vector_store():
    """
    Initialize the embedding model and ChromaDB collection.
    Called once from the FastAPI startup event so that it does not block
    the module import (which caused 5-10 s cold-start delays on Render).
    """
    global global_embedder, global_chroma
    if global_chroma is not None:
        return  # already initialised

    from langchain_chroma import Chroma

    logger.info("Initialising embedding model and ChromaDB…")
    global_embedder = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-2")
    global_chroma = Chroma(
        collection_name="tutor_lessons",
        embedding_function=global_embedder,
        persist_directory=CHROMA_PERSIST_DIR,
    )
    logger.info("ChromaDB ready.")


def _get_chroma():
    """Return the Chroma instance, raising clearly if not yet initialised."""
    if global_chroma is None:
        raise RuntimeError("Vector store not initialised. Call init_vector_store() first.")
    return global_chroma


def add_lesson_to_vector_store(course_name: str, chapter_title: str, lesson_title: str, content: str) -> bool:
    """
    Split lesson content into chunks and add them to ChromaDB.
    Returns True on success, False on failure.
    .persist() is intentionally omitted — langchain-chroma auto-persists. (fixes AI-3)
    """
    try:
        chroma = _get_chroma()
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n## ", "\n\n", "\n", ". "]
        )
        chunks = text_splitter.split_text(content)
        if not chunks:
            return True  # nothing to index is not an error
        metadatas = [{"course": course_name, "chapter": chapter_title, "lesson": lesson_title} for _ in chunks]
        chroma.add_texts(texts=chunks, metadatas=metadatas)
        return True
    except Exception as e:
        logger.error(f"Error adding lesson to ChromaDB: {e}")
        return False


def delete_course_from_vector_store(course_name: str):
    """Remove all ChromaDB documents belonging to a course."""
    try:
        chroma = _get_chroma()
        result = chroma.get(where={"course": course_name})
        if result and result.get("ids"):
            chroma.delete(ids=result["ids"])
            # .persist() intentionally omitted — auto-persists (fixes AI-3)
    except Exception as e:
        logger.error(f"Error deleting course from ChromaDB: {e}")

# ---------------------------------------------------------------------------
# RAG tutor — simple async function replacing LangGraph (fixes AI-1, AI-2)
# ---------------------------------------------------------------------------

class TutorState(TypedDict):
    question: str
    course_name: str
    chapter_title: str
    lesson_title: str
    context: str
    answer: str


async def run_tutor(question: str, course_name: str, chapter_title: str, lesson_title: str) -> str:
    """
    Retrieve relevant lesson chunks from ChromaDB then generate an answer.

    Replaces the unnecessary LangGraph StateGraph (was a 2-node linear chain
    with no branching or conditional logic — pure overhead).

    ChromaDB similarity_search is synchronous; we offload it to the threadpool
    so it does not block the async event loop. (fixes AI-1)
    """
    from fastapi.concurrency import run_in_threadpool

    # --- Retrieve ---
    try:
        chroma = _get_chroma()
        docs = await run_in_threadpool(
            chroma.similarity_search,
            question,
            k=3,
            filter={"course": course_name, "lesson": lesson_title},
        )
        context = "\n\n".join([doc.page_content for doc in docs])
    except Exception as e:
        logger.error(f"ChromaDB retrieval error: {e}")
        context = ""

    # --- Generate ---
    answer = await rag_chain.ainvoke({
        "course_name": course_name,
        "chapter_title": chapter_title,
        "lesson_title": lesson_title,
        "context": context,
        "question": question,
    })
    return answer