import markdown
from fastapi import Request
from fastapi.templating import Jinja2Templates
from database import get_db
from models import Course

templates = Jinja2Templates(directory="templates")

def markdown_filter(text):
    if not text:
        return ""
    return markdown.markdown(text, extensions=['fenced_code', 'tables'])

templates.env.filters['markdown'] = markdown_filter

def get_course_names_for_template():
    db = next(get_db())
    courses = db.query(Course).all()
    return [c.course_name for c in courses]

def get_flashed_messages(request: Request, with_categories=False):
    messages = request.session.pop('_flashes', [])
    if with_categories:
        return messages
    return [msg[1] for msg in messages]

def flash(request: Request, message: str, category: str = "message"):
    if '_flashes' not in request.session:
        request.session['_flashes'] = []
    request.session['_flashes'].append((category, message))

def render(request: Request, template_name: str, context: dict = None, status_code: int = 200):
    if context is None:
        context = {}
    context["request"] = request
    context["session"] = request.session
    context["get_course_names"] = get_course_names_for_template
    context["get_flashed_messages"] = lambda with_categories=False: get_flashed_messages(request, with_categories)
    
    def custom_url_for(name: str, **kwargs):
        if name == 'static' and 'filename' in kwargs:
            kwargs['path'] = kwargs.pop('filename')
        return request.url_for(name, **kwargs)
        
    context["url_for"] = custom_url_for
    return templates.TemplateResponse(request=request, name=template_name, context=context, status_code=status_code)
