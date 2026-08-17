import os
from typing import List, Dict
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from datetime import datetime, timedelta
import json
import logging
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.embeddings import Embeddings
from langchain_core.output_parsers import StrOutputParser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")

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

global_embedder = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-2")

from langchain_chroma import Chroma
from langgraph.graph import StateGraph, END
from typing import TypedDict

CHROMA_PERSIST_DIR = os.path.join("instance", "chroma_db")

global_chroma = Chroma(
    collection_name="tutor_lessons",
    embedding_function=global_embedder,
    persist_directory=CHROMA_PERSIST_DIR
)

def add_lesson_to_vector_store(course_name: str, chapter_title: str, lesson_title: str, content: str):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n## ", "\n\n", "\n", ". "]
    )
    chunks = text_splitter.split_text(content)
    if not chunks:
        return
    metadatas = [{"course": course_name, "chapter": chapter_title, "lesson": lesson_title} for _ in chunks]
    global_chroma.add_texts(texts=chunks, metadatas=metadatas)
    global_chroma.persist()

def delete_course_from_vector_store(course_name: str):
    try:
        # Get all document IDs for this course
        result = global_chroma.get(where={"course": course_name})
        if result and result.get("ids"):
            global_chroma.delete(ids=result["ids"])
            global_chroma.persist()
    except Exception as e:
        logger.error(f"Error deleting course from Chroma DB: {str(e)}")

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

class TutorState(TypedDict):
    question: str
    course_name: str
    chapter_title: str
    lesson_title: str
    context: str
    answer: str

def retrieve_node(state: TutorState):
    try:
        docs = global_chroma.similarity_search(
            state["question"], 
            k=3, 
            filter={"course": state["course_name"], "lesson": state["lesson_title"]}
        )
        context = "\n\n".join([doc.page_content for doc in docs])
        return {"context": context}
    except Exception as e:
        logger.error(f"Chroma DB Error: {str(e)}")
        return {"context": ""}

def generate_node(state: TutorState):
    response_chain = rag_prompt | llm
    result = response_chain.invoke({
        "course_name": state["course_name"],
        "chapter_title": state["chapter_title"],
        "lesson_title": state["lesson_title"],
        "context": state["context"],
        "question": state["question"]
    })
    return {"answer": result.content}

workflow = StateGraph(TutorState)
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("generate", generate_node)
workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "generate")
workflow.add_edge("generate", END)

tutor_app = workflow.compile()