from django import template
from erp.print_copy import caption
register=template.Library()

@register.filter
def document_copy(value,language):return caption(value,language)

@register.simple_tag(takes_context=True)
def print_text(context,value):return caption(value,context.get('print_language','bilingual'))
