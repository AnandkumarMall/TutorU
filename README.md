# TutorU

An AI-powered web application that generates personalized courses, schedules, and quizzes on any topic using Google Gemini.

TutorU allows you to type in a topic and instantly receive a fully structured curriculum. It creates chapters, writes comprehensive markdown lessons, and generates adaptive quizzes to test your knowledge. The app also features a Retrieval-Augmented Generation (RAG) AI Tutor that can answer questions based strictly on the generated lesson material without hallucinating outside facts.

**Live Demo**: [https://tutoru-1v05.onrender.com/](https://tutoru-1v05.onrender.com/)

## Architecture

TutorU is a monolith built on FastAPI, using SQLite for persistence and ChromaDB for local vector storage.

```mermaid
flowchart LR
    User([User]) -->|Creates Course| FastAPI[FastAPI App]
    FastAPI -->|Stores metadata| DB[(SQLite DB)]
    FastAPI <-->|Generates Content| Gemini[Google Gemini AI]
    FastAPI -->|Embeds lessons| Chroma[(ChromaDB Vector Store)]
    User -->|Asks Question| Tutor[AI Tutor RAG]
    Tutor <-->|Fetches Context| Chroma
    Tutor <-->|Answers| Gemini
```

## Features

- **AI Course Generation**: Auto-generates chapters, lessons, and quizzes based on a single topic prompt.
- **Smart Scheduling**: Plans out your lessons and quizzes daily.
- **Context-Aware AI Tutor**: Ask questions about specific lessons using the built-in RAG chatbot.
- **Adaptive Quizzes**: Auto-generates multiple-choice quizzes with instant grading and feedback.
- **Modern Minimal UI**: Clean, professional design built with a custom CSS framework on top of Bootstrap.

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy (SQLite)
- **AI & RAG**: LangChain, Google Gemini, ChromaDB, Sentence Transformers
- **Frontend**: Jinja2 Templates, Vanilla CSS, Bootstrap 5

## Getting Started

### Prerequisites
- Python 3.10+
- Google Gemini API Key

### Installation

1. Clone the repository:
```bash
git clone https://github.com/AnandkumarMall/TutorU.git
cd TutorU
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

3. Configure environment variables:
Create a `.env` file in the project root:
```env
GOOGLE_API_KEY=your_gemini_api_key_here
SECRET_KEY=your_secure_random_string_here
```

### Running the App

Start the FastAPI server using Uvicorn:

```bash
uvicorn main:app --reload
```

The app will be available at `http://127.0.0.1:8000`.

## Project Structure

```text
TutorU/
├── main.py             # FastAPI application entry point
├── routers/            # Route handlers (course, lesson, quiz, chat)
├── models.py           # SQLAlchemy database schemas
├── utils.py            # LangChain prompts, AI generation, and RAG logic
├── dependencies.py     # Custom Jinja2 rendering and flash messaging
├── templates/          # HTML templates
└── render.yaml         # Render deployment blueprint
```

## License

MIT License. Built by Anand Kumar Mall.
