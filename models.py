from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import json
from database import Base


class Course(Base):
    __tablename__ = 'courses'
    course_id = Column(Integer, primary_key=True)
    course_name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Tracks if the background task is currently generating lessons and schedules
    is_generating = Column(Boolean, default=True, nullable=False)

    chapters = relationship('Chapter', back_populates='course', cascade='all, delete-orphan')


class Chapter(Base):
    __tablename__ = 'chapters'
    chapter_id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey('courses.course_id'), nullable=False)
    chapter_title = Column(String(200), nullable=False)
    chapter_order = Column(Integer, nullable=False)

    course = relationship('Course', back_populates='chapters')
    lessons = relationship('Lesson', back_populates='chapter', cascade='all, delete-orphan')
    schedule_entries = relationship('Schedule', back_populates='chapter', cascade='all, delete-orphan')

    # Index: course_id filtered in course_detail and delete (fixes PERF-2)
    __table_args__ = (
        Index('ix_chapters_course_id', 'course_id'),
    )


class Lesson(Base):
    __tablename__ = 'lessons'
    lesson_id = Column(Integer, primary_key=True)
    chapter_id = Column(Integer, ForeignKey('chapters.chapter_id'), nullable=False)
    lesson_title = Column(String(200), nullable=False)
    lesson_order = Column(Integer, nullable=False)
    content = Column(Text)
    # Pre-rendered HTML from content markdown — computed once on first generation,
    # served directly on every subsequent view (eliminates per-request markdown parsing).
    # NULL means not yet rendered; router will render-and-save lazily. (fixes PERF-8)
    content_html = Column(Text, nullable=True)
    # Tracks whether this lesson's content has been successfully indexed in ChromaDB. (AI-4)
    vector_indexed = Column(Boolean, default=False, nullable=False)

    chapter = relationship('Chapter', back_populates='lessons')
    schedule_entries = relationship('Schedule', back_populates='lesson', cascade='all, delete-orphan')
    quizzes = relationship('Quiz', back_populates='lesson', cascade='all, delete-orphan')

    # Index: chapter_id filtered in lesson nav query (fixes PERF-2)
    __table_args__ = (
        Index('ix_lessons_chapter_id', 'chapter_id'),
    )


class Schedule(Base):
    __tablename__ = 'schedule'
    schedule_id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey('courses.course_id'), nullable=False)
    chapter_id = Column(Integer, ForeignKey('chapters.chapter_id'), nullable=False)
    lesson_id = Column(Integer, ForeignKey('lessons.lesson_id'))
    date = Column(String(10), nullable=False)      # YYYY-MM-DD
    task_type = Column(String(20), nullable=False)  # Lesson | Short Quiz | Large Quiz
    task_description = Column(String(300), nullable=False)

    chapter = relationship('Chapter', back_populates='schedule_entries')
    lesson = relationship('Lesson', back_populates='schedule_entries')
    todays_tasks = relationship('TodaysTask', back_populates='schedule', cascade='all, delete-orphan')

    # Composite index: date + course_id are the two most common filter combos (fixes PERF-2)
    __table_args__ = (
        Index('ix_schedule_date', 'date'),
        Index('ix_schedule_course_id', 'course_id'),
        Index('ix_schedule_date_course', 'date', 'course_id'),
    )


class TodaysTask(Base):
    __tablename__ = 'todays_tasks'
    id = Column(Integer, primary_key=True)
    date = Column(String(10), nullable=False)       # YYYY-MM-DD
    schedule_id = Column(Integer, ForeignKey('schedule.schedule_id'), nullable=False)
    task_type = Column(String(20), nullable=False)
    generation_status = Column(String(20), default='Pending')
    completed = Column(Boolean, default=False)

    schedule = relationship('Schedule', back_populates='todays_tasks')

    # Composite index: schedule_id + date queried together frequently (fixes PERF-2)
    __table_args__ = (
        Index('ix_todays_tasks_schedule_date', 'schedule_id', 'date'),
    )


class Quiz(Base):
    __tablename__ = 'quizzes'
    quiz_id = Column(Integer, primary_key=True)
    date = Column(String(10), nullable=False)       # YYYY-MM-DD
    course_id = Column(Integer, ForeignKey('courses.course_id'), nullable=False)
    chapter_id = Column(Integer, ForeignKey('chapters.chapter_id'), nullable=False)
    lesson_id = Column(Integer, ForeignKey('lessons.lesson_id'))
    quiz_type = Column(String(20), nullable=False)  # Short Quiz | Large Quiz
    question = Column(Text, nullable=False)
    options = Column(Text, nullable=False)          # JSON list
    correct_answer = Column(Text, nullable=False)
    score = Column(Integer)

    lesson = relationship('Lesson', back_populates='quizzes')

    # Composite index: the quiz view always filters on all four columns (fixes PERF-2)
    __table_args__ = (
        Index('ix_quizzes_lookup', 'course_id', 'chapter_id', 'quiz_type', 'date'),
    )

    def get_options(self):
        return json.loads(self.options)

    def set_options(self, options_list):
        self.options = json.dumps(options_list)