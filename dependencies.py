import markdown as md_module
from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

templates = Jinja2Templates(directory="templates")


def markdown_filter(text):
    """Jinja2 filter: render markdown to HTML. Used for fallback rendering in templates."""
    if not text:
        return ""
    return md_module.markdown(text, extensions=['fenced_code', 'tables'])


def render_markdown(text: str) -> str:
    """Render markdown to HTML. Used server-side before storing content_html."""
    if not text:
        return ""
    return md_module.markdown(text, extensions=['fenced_code', 'tables'])


templates.env.filters['markdown'] = markdown_filter


def get_flashed_messages(request: Request, with_categories=False):
    messages = request.session.pop('_flashes', [])
    if with_categories:
        return messages
    return [msg[1] for msg in messages]


def flash(request: Request, message: str, category: str = "message"):
    if '_flashes' not in request.session:
        request.session['_flashes'] = []
    request.session['_flashes'].append((category, message))


async def get_course_names(db: AsyncSession) -> list[str]:
    """
    Return a list of all course names.

    Async — callers must await this. Uses the provided session so no
    extra connection is opened (fixed session leak from PERF-1).
    """
    from models import Course
    result = await db.execute(select(Course.course_name))
    return [row[0] for row in result.all()]


def render(request: Request, template_name: str, context: dict = None, status_code: int = 200):
    if context is None:
        context = {}
    context["request"] = request
    context["session"] = request.session
    context["get_flashed_messages"] = lambda with_categories=False: get_flashed_messages(request, with_categories)

    def custom_url_for(name: str, **kwargs):
        if name == 'static' and 'filename' in kwargs:
            kwargs['path'] = kwargs.pop('filename')
        return request.url_for(name, **kwargs)

    context["url_for"] = custom_url_for
    return templates.TemplateResponse(request=request, name=template_name, context=context, status_code=status_code)
