"""Validated appearance settings; never editable financial layout or HTML."""
import base64
import binascii
from copy import deepcopy
from io import BytesIO
import re
from django.core.exceptions import ValidationError
from PIL import Image

FAMILIES=('invoice','quotation','order','receipt','purchase_bill','payroll','transfer','other')
LANGUAGES={'bilingual','fa','ps','en'}

def family(kind):
    if kind in {'sale','fx_sale'}:return 'invoice'
    if kind=='quotation':return 'quotation'
    if kind in {'sales_order','purchase_order'}:return 'order'
    if kind in {'purchase_bill','fx_purchase'}:return 'purchase_bill'
    if kind.startswith('payroll') or kind=='employee_advance':return 'payroll'
    if kind.startswith('transfer_') or kind=='internal_settlement':return 'transfer'
    if kind in {'receipt','supplier_payment','customer_refund','supplier_refund','fx_settle'}:return 'receipt'
    return 'other'

def logo(value):
    if value=='':return ''
    if not isinstance(value,str) or len(value)>350000:raise ValidationError('Upload a PNG or JPEG logo no larger than 512 pixels and 250 KB.')
    match=re.fullmatch(r'data:image/(png|jpeg);base64,([A-Za-z0-9+/=\r\n]+)',value)
    if not match:raise ValidationError('Upload a PNG or JPEG logo no larger than 512 pixels and 250 KB.')
    try:
        raw=base64.b64decode(match[2],validate=True)
        if len(raw)>250000:raise ValueError()
        with Image.open(BytesIO(raw)) as source:
            if source.format not in {'PNG','JPEG'} or max(source.size)>512 or min(source.size)<1 or getattr(source,'n_frames',1)!=1:raise ValueError()
            source.load();clean=Image.new('RGBA',source.size);clean.paste(source.convert('RGBA'));output=BytesIO();clean.save(output,format='PNG',optimize=True)
        if len(output.getvalue())>250000:raise ValueError()
        return 'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode('ascii')
    except (ValueError,OSError,binascii.Error,Image.DecompressionBombError):
        raise ValidationError('Upload a PNG or JPEG logo no larger than 512 pixels and 250 KB.')

def validate_advanced(profile):
    result=deepcopy(profile)
    if 'document_language' in result and (not isinstance(result['document_language'],str) or result['document_language'] not in LANGUAGES):raise ValidationError('Select a supported document language.')
    if 'logo_data_url' in result:result['logo_data_url']=logo(result['logo_data_url'])
    if 'document_templates' in result:
        templates=result['document_templates']
        if not isinstance(templates,dict) or set(templates)-set(FAMILIES):raise ValidationError('Select valid document-specific templates.')
        text={'title_dari':150,'title_english':150,'title_pashto':150,'footer':1000,'payment_instructions':1000,'signature_left':120,'signature_right':120}
        for template in templates.values():
            if not isinstance(template,dict) or set(template)-set(text)-{'show_signatures','paper'}:raise ValidationError('Select valid document-specific template fields.')
            for key,value in template.items():
                if key in text and (not isinstance(value,str) or len(value)>text[key]):raise ValidationError('Document template text exceeds its allowed length.')
                if key=='show_signatures' and not isinstance(value,bool):raise ValidationError('Select whether this document shows signatures.')
                if key=='paper' and (not isinstance(value,str) or value not in {'','A4','80mm'}):raise ValidationError('Select A4 or 80mm receipt paper.')
    if 'printer_profiles' in result:
        profiles=result['printer_profiles']
        if not isinstance(profiles,list) or len(profiles)>8:raise ValidationError('Configure no more than eight printer profiles.')
        seen=set()
        for item in profiles:
            if not isinstance(item,dict) or set(item)-{'id','name','paper','margin_mm','hardware_note'}:raise ValidationError('Select valid printer-profile fields.')
            ident=item.get('id','')
            if not isinstance(ident,str) or not re.fullmatch(r'[a-z0-9_-]{1,40}',ident) or ident in seen:raise ValidationError('Printer profile IDs must be valid and unique.')
            seen.add(ident)
            if not isinstance(item.get('name'),str) or not item['name'].strip() or len(item['name'])>100:raise ValidationError('Enter a printer profile name of at most 100 characters.')
            if not isinstance(item.get('paper'),str) or item.get('paper') not in {'A4','80mm'}:raise ValidationError('Select A4 or 80mm receipt paper.')
            margin=item.get('margin_mm')
            if type(margin) is not int or not 3<=margin<=20:raise ValidationError('Printer margins must be whole millimeters between 3 and 20.')
            if not isinstance(item.get('hardware_note',''),str) or len(item.get('hardware_note',''))>200:raise ValidationError('Printer hardware notes are limited to 200 characters.')
    return result

def effective(profile,kind,params):
    result=deepcopy(profile);group=family(kind);template=result.get('document_templates',{}).get(group,{})
    result.update({k:v for k,v in template.items() if k in {'footer','payment_instructions','signature_left','signature_right','show_signatures'} and v!=''})
    lang=params.get('language') or result.get('document_language','bilingual')
    if lang not in LANGUAGES:raise ValidationError('Select a supported document language.')
    printer=None
    if params.get('printer'):
        printer=next((p for p in result.get('printer_profiles',[]) if p['id']==params['printer']),None)
        if not printer:raise ValidationError('Select a printer profile belonging to this business.')
    compact_default=kind in {'receipt','supplier_payment','customer_refund','supplier_refund','employee_advance','payroll_settle','fx_settle'} and result.get('receipt_paper')=='80mm'
    paper=printer['paper'] if printer else template.get('paper') or ('80mm' if compact_default else 'A4')
    if 'compact' in params:
        if params['compact'] not in {'0','1'}:raise ValidationError('Select a valid compact printing option.')
        paper='80mm' if params['compact']=='1' else 'A4'
    return {'profile':result,'template':template,'family':group,'language':lang,'compact':paper=='80mm','paper':paper,'margin_mm':printer['margin_mm'] if printer and printer['paper']==paper else 4 if paper=='80mm' else 14,'printer':printer['id'] if printer else None}
