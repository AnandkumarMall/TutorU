from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
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

class Lesson(Base):
    __tablename__ = 'lessons'
    lesson_id = Column(Integer, primary_key=True)
    chapter_id = Column(Integer, ForeignKey('chapters.chapter_id'), nullable=False)
    lesson_title = Column(String(200), nullable=False)
    lesson_order = Column(Integer, nullable=False)
    content = Column(Text)
    
    chapter = relationship('Chapter', back_populates='lessons')
    schedule_entries = relationship('Schedule', back_populates='lesson', cascade='all, delete-orphan')
    quizzes = relationship('Quiz', back_populates='lesson', cascade='all, delete-orphan')

class Schedule(Base):
    __tablename__ = 'schedule'
    schedule_id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey('courses.course_id'), nullable=False)
    chapter_id = Column(Integer, ForeignKey('chapters.chapter_id'), nullable=False)
    lesson_id = Column(Integer, ForeignKey('lessons.lesson_id'))
    date = Column(String(10), nullable=False) 
    task_type = Column(String(20), nullable=False) 
    task_description = Column(String(300), nullable=False)
    
    chapter = relationship('Chapter', back_populates='schedule_entries')
    lesson = relationship('Lesson', back_populates='schedule_entries')
    todays_tasks = relationship('TodaysTask', back_populates='schedule', cascade='all, delete-orphan')

class TodaysTask(Base):
    __tablename__ = 'todays_tasks'
    id = Column(Integer, primary_key=True)
    date = Column(String(10), nullable=False)  
    schedule_id = Column(Integer, ForeignKey('schedule.schedule_id'), nullable=False)
    task_type = Column(String(20), nullable=False)
    generation_status = Column(String(20), default='Pending')  
    completed = Column(Boolean, default=False)
    
    schedule = relationship('Schedule', back_populates='todays_tasks')

class Quiz(Base):
    __tablename__ = 'quizzes'
    quiz_id = Column(Integer, primary_key=True)
    date = Column(String(10), nullable=False)
    course_id = Column(Integer, ForeignKey('courses.course_id'), nullable=False)
    chapter_id = Column(Integer, ForeignKey('chapters.chapter_id'), nullable=False)
    lesson_id = Column(Integer, ForeignKey('lessons.lesson_id'))
    quiz_type = Column(String(20), nullable=False)  
    question = Column(Text, nullable=False)
    options = Column(Text, nullable=False)  
    correct_answer = Column(Text, nullable=False)
    score = Column(Integer)
    
    lesson = relationship('Lesson', back_populates='quizzes')
    
    def get_options(self):
        return json.loads(self.options)
    
    def set_options(self, options_list):
        self.options = json.dumps(options_list)