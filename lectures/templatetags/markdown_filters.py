"""Markdown rendering filters."""
import markdown
from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def markdown_to_html(text):
    """Convert markdown text to HTML."""
    if not text:
        return ""
    
    html = markdown.markdown(
        text,
        extensions=[
            'markdown.extensions.tables',
            'markdown.extensions.fenced_code',
            'markdown.extensions.codehilite',
            'markdown.extensions.toc',
        ]
    )
    return mark_safe(html)
