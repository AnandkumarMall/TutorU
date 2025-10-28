# TutorU

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/Flask-2.0%2B-green.svg)](https://flask.palletsprojects.com/)
[![Flask-SQLAlchemy](https://img.shields.io/badge/Flask--SQLAlchemy-3.0%2B-orange.svg)](https://flask-sqlalchemy.palletsprojects.com/)
[![python-dotenv](https://img.shields.io/badge/python--dotenv-1.0%2B-green.svg)](https://github.com/theskumar/python-dotenv)
[![Markdown](https://img.shields.io/badge/Markdown-3.4%2B-blue.svg)](https://python-markdown.github.io/)
[![Pydantic](https://img.shields.io/badge/Pydantic-2.4%2B-red.svg)](https://docs.pydantic.dev/)
[![Sentence Transformers](https://img.shields.io/badge/Sentence%20Transformers-2.2%2B-yellow.svg)](https://www.sbert.net/)
[![LangChain](https://img.shields.io/badge/LangChain-black.svg)](https://python.langchain.com/docs/get_started/introduction)
[![LangChain Community](https://img.shields.io/badge/LangChain%20Community-lightgrey.svg)](https://python.langchain.com/docs/integrations/providers/community/)
[![LangChain Core](https://img.shields.io/badge/LangChain%20Core-darkblue.svg)](https://python.langchain.com/docs/modules/model_io/)
[![LangChain Google GenAI](https://img.shields.io/badge/LangChain%20Google%20GenAI-purple.svg)](https://python.langchain.com/docs/integrations/llms/google_ai/)
[![FAISS CPU](https://img.shields.io/badge/FAISS%20CPU-1.7%2B-blue.svg)](https://github.com/facebookresearch/faiss)
[![Gunicorn](https://img.shields.io/badge/Gunicorn-21.0%2B-green.svg)](https://gunicorn.org/)

<div align="center">
  <img src="https://via.placeholder.com/800x400/2d5a8c/f7f4f0?text=TutorU+-+AI-Powered+Learning+Platform" alt="TutorU Banner">
  <br><br>
</div>

**TutorU** is an AI-powered web application built with Flask that empowers users to create, schedule, and learn from personalized online courses. Leveraging Google's Gemini AI (via LangChain), it generates structured courses with chapters, lessons, and quizzes tailored to any topic. Features include interactive lesson viewing with an AI tutor, adaptive quizzes, and daily task scheduling to keep learners on track. Perfect for educators, self-learners, or anyone building knowledge paths efficiently.

> **Demo**: [Live Preview](https://your-app-url.com) (Deployed on Heroku/Render – update with your link)  
> **Tech Stack**: Flask, SQLAlchemy (SQLite), LangChain, Google Gemini AI, Bootstrap 5, FAISS (for RAG), Sentence Transformers.

## 🚀 Features

- **AI-Driven Course Generation** 🎓  
  - Input a course topic (e.g., "Python for Beginners") to auto-generate 5 chapters and 3 lessons per chapter.  
  - Select and customize chapters before creation.

- **Structured Learning Paths** 📅  
  - Daily schedules with lessons and quizzes (short: 5 questions; large: 10 questions).  
  - Mark tasks as completed to unlock progress tracking.

- **Interactive Lessons** 💬  
  - Rendered Markdown content with headings, lists, code blocks, and examples.  
  - Built-in AI Tutor (RAG-powered) for Q&A based solely on lesson content – no external knowledge drift.

- **Quizzes & Assessment** 📝  
  - Multiple-choice quizzes with 4 options per question.  
  - Instant scoring, grading (A-F), and feedback modal.  
  - Beginner-friendly questions with explanations.

- **User-Friendly Dashboard** 🏠  
  - Home page shows today's tasks by course.  
  - Course detail view with accordion-style chapters, lessons, and schedules.  
  - Responsive design (mobile-friendly) with Bootstrap 5 and custom warm, professional theming.

- **Advanced Tech Under the Hood** ⚙️  
  - Retrieval-Augmented Generation (RAG) using FAISS vector store for precise, context-aware AI responses.  
  - Persistent data with SQLite (easy to scale to PostgreSQL).  
  - Flash messages, form validation, and loading states for smooth UX.

| Feature                  | Description                                      | AI Integration                  |
|--------------------------|--------------------------------------------------|---------------------------------|
| **Course Creation**      | Generate & select chapters/lessons               | Gemini for structured JSON     |
| **Lesson Viewing**       | Markdown-rendered content + chat                 | RAG with Sentence Transformers |
| **Quizzes**              | Auto-generated MCQs                              | Gemini for question variety    |
| **Scheduling**           | Daily tasks (lessons + quizzes)                  | Rule-based from lesson structure |
| **Progress Tracking**    | Mark complete, hide done tasks                   | Flask sessions + DB            |

## 🛠️ Setup & Installation

### Prerequisites
- Python 3.8+  
- Google Gemini API Key (free tier available at [Google AI Studio](https://aistudio.google.com/))  
- Git

### Step-by-Step Installation
1. **Clone the Repository**:
   ```bash
   git clone https://github.com/yourusername/tutoru.git
   cd tutoru
   ```

2. **Create Virtual Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   *Note*: Create `requirements.txt` if missing (generated via `pip freeze > requirements.txt`). Key packages:
   ```
   Flask==2.3.3
   Flask-SQLAlchemy==3.0.5
   langchain-google-genai==0.0.7
   langchain-core==0.1.0
   sentence-transformers==2.2.2
   faiss-cpu==1.7.4
   python-dotenv==1.0.0
   markdown==3.4.1
   pydantic==2.4.2
   gunicorn==21.2.0
   ```

4. **Set Up Environment Variables**:
   Create a `.env` file in the root:
   ```
   GOOGLE_API_KEY=your_gemini_api_key_here
   SECRET_KEY=your_flask_secret_key_here  # Generate with: python -c "import secrets; print(secrets.token_hex(16))"
   ```

5. **Initialize Database**:
   ```bash
   python app.py  # Runs init_db() automatically on first start
   ```
   *DB File*: `courses.db` (SQLite – migrates easily to SQLAlchemy-supported DBs).

6. **Run the App**:
   ```bash
   python app.py
   ```
   - Access at `http://127.0.0.1:5000`  
   - Debug mode: `FLASK_ENV=development python app.py`  
   - Production: `gunicorn app:app`

### Docker (Optional)
For containerized setup:
```dockerfile
# Dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
```
Build & Run:
```bash
docker build -t tutoru .
docker run -p 5000:5000 --env-file .env tutoru
```

## 📖 Usage

1. **Create a New Course** (`/new_course`):  
   - Enter a topic (e.g., "Machine Learning Basics").  
   - AI generates 5 chapters → Select 1+ → Submit to auto-create lessons & schedule.

2. **Dashboard** (`/`):  
   - View "Today's Tasks" grouped by course.  
   - Click "Start" on lessons/quizzes → Mark complete to progress.

3. **View Course** (`/course/<course_name>`):  
   - Expand chapters to see lessons & scheduled tasks.  
   - Tasks locked until due date.

4. **Read Lessons** (`/lesson/<course_name>/<chapter_id>/<lesson_id>`):  
   - View generated content.  
   - Chat with AI Tutor: Ask questions → Get context-specific answers.

5. **Take Quizzes** (`/quiz/<course_name>/<chapter_id>[/<lesson_id>]`):  
   - Navigate questions with prev/next.  
   - Submit for score & feedback (e.g., 85% = B grade).

**API Endpoints** (for extensions):  
- `POST /ask_question`: RAG-based Q&A.  
- `POST /submit_quiz`: Save scores.  
- `POST /mark_task_completed`: Update progress.

**Pro Tips** 🌟:  
- Lessons auto-generate on first view (lazy-loading).  
- Quizzes cache questions daily to avoid regeneration.  
- Customize themes in `base.html` CSS variables.

## 🏗️ Project Architecture

```
tutoru/
├── app.py              # Flask routes & logic
├── models.py           # SQLAlchemy DB models
├── utils.py            # LangChain chains, RAG setup
├── templates/          # Jinja2 HTML (base.html, home.html, etc.)
├── static/             # CSS/JS (if added)
├── requirements.txt    # Dependencies
├── .env                # Secrets
└── courses.db          # SQLite DB
```

- **Frontend**: Bootstrap 5 + Custom CSS (warm palette: blues, creams).  
- **Backend**: Flask + SQLAlchemy ORM.  
- **AI Pipeline**: LangChain → Gemini → Structured JSON parsing.  
- **Data Flow**: User input → AI Chain → DB Save → Render Template.

## 🤝 Contributing

We welcome contributions! Help make TutorU even smarter and more accessible.

### How to Contribute
1. **Fork & Clone**:
   ```bash
   git fork https://github.com/yourusername/tutoru
   git clone https://github.com/YOUR_USERNAME/tutoru.git
   ```

2. **Create a Branch**:
   ```bash
   git checkout -b feature/amazing-new-feature
   ```

3. **Make Changes**:
   - Add tests (use `pytest` – add to requirements).  
   - Update docs/README.  
   - Follow PEP8 style (use `black` formatter).

4. **Commit & Push**:
   ```bash
   git add .
   git commit -m "Add amazing new feature"
   git push origin feature/amazing-new-feature
   ```

5. **Pull Request**:
   - Open PR to `main` branch.  
   - Describe changes, reference issues.

### Guidelines
- **Issues**: Bug reports, feature requests → Use GitHub Issues.  
- **Code Style**: PEP8, 4-space indents.  
- **Testing**: Add unit tests for new chains/routes.  
- **Changelog**: Update `CHANGELOG.md` for releases.  
- **No Breaking Changes**: Deprecate, don't delete.

**Credit**: Built with ❤️ by [Anand Kumar Mall](https://github.com/AnandkumarMall). Contributions from the open-source community.


**Star this repo if it helps your learning journey! 🌟**  
*Last Updated: October 28, 2025*
