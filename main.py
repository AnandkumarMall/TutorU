from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import os

from database import engine, Base
import models

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI()

secret_key = os.environ.get('SECRET_KEY')
if not secret_key:
    if os.environ.get('ENVIRONMENT') == 'production':
        raise ValueError("SECRET_KEY environment variable is not set in production!")
    import secrets
    secret_key = secrets.token_hex(16)

app.add_middleware(SessionMiddleware, secret_key=secret_key)
app.mount("/static", StaticFiles(directory="static"), name="static")

from routers import home, course, lesson, quiz, chat

app.include_router(home.router)
app.include_router(course.router)
app.include_router(lesson.router)
app.include_router(quiz.router)
app.include_router(chat.router)

from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi import Request
from dependencies import render
import logging

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return render(request, "404.html", status_code=404)
    return render(request, "500.html", status_code=exc.status_code)

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logging.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return render(request, "500.html", status_code=500)
