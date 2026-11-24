"""Separate display-language names without changing financial document snapshots."""
import re
from django.core.exceptions import ValidationError

ARABIC=re.compile(r'[\u0620-\u064a\u066e-\u06d3\u06fa-\u06ff]')
LATIN=re.compile(r'[A-Za-z]')

def language_name(obj,language='fa'):
    language=str(language).split('-')[0]
    return getattr(obj,'name_'+language,'') or getattr(obj,'name_fa','') or obj.name

def prepare_name_payload(obj,data):
    """Keep legacy name-only API callers working; never join translated names."""
    if 'name' in data and not any(key in data for key in ('name_fa','name_en','name_ps')):
        value=str(data['name']).strip()
        if ARABIC.search(value) and LATIN.search(value):
            raise ValidationError('Enter Dari and English names in separate fields.')
        key='name_fa' if ARABIC.search(value) else 'name_en'
        data[key]=value
        # A legacy name updates its own language; other translations are retained.
    names={key:str(data.get(key,getattr(obj,key,'')) or '').strip() for key in ('name_fa','name_en','name_ps')}
    data.update({key:value for key,value in names.items() if key in data})
    canonical=names['name_fa'] or names['name_ps'] or names['name_en'] or str(data.get('name',obj.name)).strip()
    if ARABIC.search(canonical) and LATIN.search(canonical):
        raise ValidationError('Enter Dari and English names in separate fields.')
    data['name']=canonical

def validate_names(obj):
    errors={}
    for key in ('name_fa','name_en','name_ps'):
        value=getattr(obj,key,'')
        if value and ((key=='name_en' and ARABIC.search(value)) or (key!='name_en' and LATIN.search(value))):
            errors[key]='Enter Dari and English names in separate fields.'
        if re.search(r'--\s*(?:کدام|كدام)\s*$',value):errors[key]='Remove the placeholder suffix from the name.'
    if ARABIC.search(obj.name) and LATIN.search(obj.name):errors['name']='Enter Dari and English names in separate fields.'
    if errors:raise ValidationError(errors)
