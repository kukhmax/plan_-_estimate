"""HTML from a template and a view model (Stage 15B). Pure: no network, no database, no clock.

Autoescape is on and an undefined value is an error, so a missing field can never print as an empty string and a name
with markup in it (a client called `<b>x</b>`) cannot break the page.
"""

from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any

from jinja2 import FileSystemLoader, StrictUndefined
from jinja2.exceptions import TemplateError
from jinja2.sandbox import SandboxedEnvironment
from markupsafe import Markup

from app.domain.documents import formatting
from app.domain.documents.labels import Labels
from app.domain.documents.layout import DocumentLayout
from app.domain.documents.registry import DocumentTemplate
from app.domain.exceptions import DocumentTemplateError

PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
FONTS_DIR = PACKAGE_DIR / "fonts"
CSS_TEMPLATE = "document.css.j2"


def _environment(*, autoescape: bool) -> SandboxedEnvironment:
    env = SandboxedEnvironment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=autoescape,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(
        money=formatting.format_money,
        qty=formatting.format_quantity,
        area=formatting.format_area,
        percent=formatting.format_percent,
        date=formatting.format_date,
        datetime=formatting.format_datetime,
    )
    return env


@cache
def _html_env() -> SandboxedEnvironment:
    return _environment(autoescape=True)


@cache
def _css_env() -> SandboxedEnvironment:
    return _environment(autoescape=False)


def render_html(template: DocumentTemplate, context: Mapping[str, Any]) -> str:
    layout = context.get("layout")
    if not isinstance(layout, DocumentLayout):
        raise DocumentTemplateError("the context must carry a `layout` (DocumentLayout)")
    labels = Labels()
    try:
        css = _css_env().get_template(CSS_TEMPLATE).render(t=labels, fonts_url=FONTS_DIR.as_uri())
        return _html_env().get_template(template.file).render(**context, t=labels, css=Markup(css))
    except DocumentTemplateError:
        raise
    except TemplateError as exc:
        raise DocumentTemplateError(f"template {template.file!r}: {exc}") from exc
