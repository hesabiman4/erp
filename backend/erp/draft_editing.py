"""Non-posting structured edits with optimistic concurrency and scoped undo."""
import base64,hashlib,hmac,json,re
from copy import deepcopy
from datetime import date
from cryptography.fernet import Fernet,InvalidToken
from django.conf import settings
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from .core import D,get_obj,get_product,json_value,registry
from .models import Document,AuditEvent,Business,Product,Warehouse,Location,Party,Employee,Block,BOM,Asset

LABELS={'date':'تاریخ سند','warehouse':'انبار','location':'موقعیت','party':'طرف حساب','supplier':'تأمین‌کننده','customer':'مشتری','employee':'کارمند','lines':'اقلام','inputs':'مصرف واقعی مواد','outputs':'خروجی تولید','blocks':'بلوک‌ها','product':'محصول','block':'بلوک مشخص','quantity':'مقدار','unit_price':'نرخ فروش','price':'نرخ','cost':'بها','amount':'مبلغ','paid':'مبلغ دریافت فعلی (AFN)','notes':'یادداشت','reason':'دلیل','reference':'مرجع','cash_account':'حساب صندوق','cash_instrument':'صندوق مستقل','bank_instrument':'حساب بانکی مستقل','thickness_mm':'ضخامت ورق (mm)','sheet_count':'تعداد ورق','length_mm':'طول','width_mm':'عرض','height_mm':'ارتفاع','due_date':'تاریخ سررسید','customer_name':'نام مشتری حضوری','phone':'شماره تماس','labor_cost':'کار مستقیم واجد شرایط (AFN)','overhead_cost':'سربار تولید واجد شرایط (AFN)','abnormal_loss':'زیان غیرعادی تأییدشده (AFN)','invoice':'بل فروش','order':'سفارش','receipt':'رسید خرید','destination':'به انبار','internal_charge':'قیمت داخلی شعبه (۰ = انتقال ساده)','debit':'بدهکار','credit':'بستانکار','account':'حساب','entries':'ردیف‌های سند','bom':'نسخه فرمول تأییدشده','lot':'لات مواد','period':'دوره معاش (YYYY-MM)'}
REFERENCES={'warehouse':Warehouse,'destination':Warehouse,'location':Location,'party':Party,'customer':Party,'supplier':Party,'employee':Employee,'product':Product,'block':Block,'bom':BOM,'asset':Asset,
            **{key:Document for key in ('invoice','order','receipt','quotation','payroll','batch','transfer','payment','exposure_document')}}
PROTECTED={'capture_review','crm_opportunity','_capture','_capture_review','source_review','source_hash'}
DECIMAL=re.compile(r'(^|_)(amount|quantity|price|cost|height|width|length|thickness|count|paid|debit|credit|loss|rate|weight|recovery|charge|value|gross|net|days|hours|pay)(_|$)')
LABELS.update({'tax_rule':'قاعده مالیاتی مؤثر (اختیاری)','line':'خط محصول','profile':'اندازه سازگار','supplier_invoice':'شماره بل تأمین‌کننده','cash_instrument':'صندوق مستقل','bank_instrument':'حساب بانکی مستقل','from_instrument':'صندوق مبدأ','to_instrument':'صندوق مقصد','from_account':'از حساب','to_account':'به حساب','from_location':'از موقعیت','to_location':'به موقعیت','cost_weight':'وزن تخصیص هزینه تأییدشده','loss_mm':'ضایعات برش (mm)','cutting_loss_mm':'ضایعات کل برش (mm)','main_height_mm':'ارتفاع بلوک آماده فروش (mm)','top_height_mm':'سربلوک (mm)','bottom_height_mm':'کف بلوک (mm)','main_cost':'بهای خروجی اصلی (اختیاری)','conversion_sources':'شناسه اسناد کار و سربار ثبت‌شده (با کاما جدا)','advance_recovery':'کسر پیش‌پرداخت مجاز (AFN)','pay':'پرداخت نقدی معاش (AFN)','gross':'معاش ناخالص','days':'روزهای حضور تأییدشده','hours':'ساعت‌های حضور تأییدشده','counted':'موجودی شمارش‌شده','description':'شرح عملیات','payment_method':'روش معمول پرداخت','rate':'نرخ','terms':'شرایط','sheet_length_mm':'طول ورق (mm)','sheet_width_mm':'عرض ورق (mm)','thickness_unit':'واحد ضخامت','planned_quantity':'مقدار برنامه تولید'})

def token(doc):
    body=json.dumps(json_value({'id':doc.pk,'state':doc.state,'data':doc.data}),sort_keys=True,separators=(',',':')).encode()
    return hmac.new(settings.SECRET_KEY.encode(),body,hashlib.sha256).hexdigest()

def cipher():return Fernet(base64.urlsafe_b64encode(hashlib.sha256((settings.SECRET_KEY+'erp-draft-undo-v1').encode()).digest()))

def editable(ctx,identifier):
    from .api import doc_permission
    from .capture_models import CaptureReview
    ctx.require('drafts.create');doc=get_obj(ctx,Document,identifier);doc_permission(ctx,doc)
    ctx.require(registry()[doc.kind][0])
    if doc.state!='draft':raise ValidationError('Only an unposted draft can be edited or restored.')
    if doc.created_by_id!=ctx.user.pk and not ctx.has('drafts.manage'):raise PermissionDenied('Edit your own draft or request draft-management permission.')
    if CaptureReview.objects.filter(draft=doc).exists():raise ValidationError('This draft was sealed by evidence review and cannot be silently changed.')
    return doc

def node(key,value):
    label=LABELS.get(key,key.replace('_',' '));base={'key':key,'label':label}
    if key in PROTECTED or key.startswith('_') or key.endswith('_id'):return {**base,'type':'protected'}
    if isinstance(value,dict):return {**base,'type':'group','fields':[node(k,v) for k,v in value.items()]}
    if isinstance(value,list):
        template=deepcopy(value[0]) if value else ({'product':'','quantity':''} if key in {'lines','inputs','outputs'} else {'length_mm':'','width_mm':'','height_mm':''} if key=='blocks' else None)
        return {**base,'type':'list','items':[node(str(i),v) for i,v in enumerate(value)],'template':template}
    if isinstance(value,bool):return {**base,'type':'checkbox'}
    if key in REFERENCES:return {**base,'type':'reference','resource':{'Warehouse':'warehouses','Location':'locations','Product':'products','Party':'parties','Employee':'employees','BOM':'boms','Block':'blocks','Asset':'assets','Document':'documents'}[REFERENCES[key].__name__]}
    if key.endswith('date') or key in {'starts','ends'}:return {**base,'type':'date'}
    if isinstance(value,(int,float)) or DECIMAL.search(key):return {**base,'type':'decimal'}
    return {**base,'type':'textarea' if key in {'notes','reason','description','address'} else 'text'}

def view(ctx,identifier):
    from .api import public_result
    doc=editable(ctx,identifier);visible=public_result(ctx,doc,doc.data)
    return {'id':doc.pk,'kind':doc.kind,'number':doc.number,'version':token(doc),'data':visible,'fields':[node(k,v) for k,v in visible.items()], 'financial_effect':False}

def merge(ctx,original,changes,key=''):
    if key in PROTECTED or key.startswith('_') or key.endswith('_id'):
        if changes!=original:raise ValidationError('System-managed draft references cannot be edited.')
        return original
    if isinstance(original,dict):
        if not isinstance(changes,dict):raise ValidationError('Use the structured draft fields.')
        if set(changes)-set(original):raise ValidationError('Unknown draft field; recreate it through the original operation form.')
        result=deepcopy(original)
        for k,v in changes.items():result[k]=merge(ctx,original[k],v,k)
        return result
    if isinstance(original,list):
        if not isinstance(changes,list) or len(changes)>1000:raise ValidationError('Draft lists must contain at most1000 rows.')
        template=original[0] if original else node(key,original)['template']
        if changes and template is None:raise ValidationError('No safe row template is available; use the original operation form.')
        return [merge(ctx,original[i] if i<len(original) else template,value,key) for i,value in enumerate(changes)]
    if isinstance(changes,(dict,list)) or isinstance(changes,float):raise ValidationError('Use exact decimal strings and individual draft fields.')
    if changes not in ('',None):
        if key in REFERENCES:
            obj=get_product(ctx,changes) if key=='product' else get_obj(ctx,REFERENCES[key],changes)
            if key=='block':get_product(ctx,obj.product_id)
        if key.endswith('date') or key in {'starts','ends'}:
            try:date.fromisoformat(str(changes))
            except ValueError:raise ValidationError('Use a valid canonical document date.')
        elif DECIMAL.search(key) and not isinstance(changes,bool):D(changes)
    return changes

def visible_fields(visible,changes):
    if isinstance(changes,dict):
        if not isinstance(visible,dict) or set(changes)-set(visible):raise PermissionDenied('Hidden draft fields cannot be edited.')
        for key,value in changes.items():visible_fields(visible[key],value)
    elif isinstance(changes,list):
        if not isinstance(visible,list):raise PermissionDenied('Hidden draft fields cannot be edited.')
        if not visible and changes:return
        for index,value in enumerate(changes):visible_fields(visible[index] if index<len(visible) else visible[0],value)

@transaction.atomic
def save(ctx,identifier,changes,version):
    from .api import public_result
    Business.objects.select_for_update().get(pk=ctx.business.pk);doc=editable(ctx,identifier)
    if not isinstance(version,str) or not hmac.compare_digest(token(doc),version):raise ValidationError('This draft changed elsewhere. Reload it before saving.')
    if not isinstance(changes,dict) or len(json.dumps(changes))>1000000:raise ValidationError('Use a bounded structured draft.')
    visible=public_result(ctx,doc,doc.data)
    visible_fields(visible,changes)
    before=deepcopy(doc.data);ctx.lines.clear();doc.data=merge(ctx,doc.data,changes)
    merge(ctx,doc.data,doc.data)
    # Freeze scope metadata to the edited references without posting anything.
    doc.location=get_obj(ctx,Location,doc.data['location']) if doc.data.get('location') else None
    doc.warehouse=get_obj(ctx,Warehouse,doc.data['warehouse']) if doc.data.get('warehouse') else None
    if doc.warehouse:doc.location=doc.warehouse.location
    if doc.data.get('line'):
        if not ctx.line_allowed(doc.data['line']):raise PermissionDenied('Product line is outside your assignment.')
        ctx.lines.add(doc.data['line'])
    for group in ('lines','inputs','outputs'):
        for row in doc.data.get(group,[]):
            if row.get('product'):get_product(ctx,row['product'])
    doc.product_lines=sorted(ctx.lines)
    if doc.data.get('date'):doc.date=date.fromisoformat(str(doc.data['date']))
    doc.party=next((get_obj(ctx,Party,doc.data[key]) for key in ('party','supplier','customer') if doc.data.get(key)),None)
    doc.employee=get_obj(ctx,Employee,doc.data['employee']) if doc.data.get('employee') else None
    doc.save(update_fields=['data','date','party','employee','location','warehouse','product_lines'])
    encrypted=cipher().encrypt(json.dumps(json_value(before),separators=(',',':')).encode()).decode()
    event=AuditEvent.objects.create(business=ctx.business,user=ctx.user,action='draft.edit',target=str(doc.pk),details={'before_encrypted':encrypted,'after_version':token(doc),'financial_effect':False})
    return {**view(ctx,doc.pk),'undo_event':event.pk}

@transaction.atomic
def undo(ctx,identifier,event_id):
    Business.objects.select_for_update().get(pk=ctx.business.pk);doc=editable(ctx,identifier)
    event=get_obj(ctx,AuditEvent,event_id)
    if event.action!='draft.edit' or event.target!=str(doc.pk) or event.user_id!=ctx.user.pk:raise PermissionDenied('Undo must refer to your own edit of this draft.')
    if AuditEvent.objects.filter(business=ctx.business,action='draft.undo',details__source_event=event.pk).exists():raise ValidationError('This edit was already undone.')
    if not hmac.compare_digest(token(doc),event.details.get('after_version','')):raise ValidationError('The draft changed after this edit. Reload and review the latest fields.')
    try:previous=json.loads(cipher().decrypt(event.details['before_encrypted'].encode()))
    except (InvalidToken,KeyError,ValueError):raise ValidationError('This undo record cannot be restored; use the current structured fields.')
    # The restored references are authorized again under current membership.
    ctx.lines.clear();merge(ctx,previous,previous)
    if previous.get('line'):
        if not ctx.line_allowed(previous['line']):raise PermissionDenied('Product line is outside your assignment.')
        ctx.lines.add(previous['line'])
    doc.data=previous;doc.product_lines=sorted(ctx.lines)
    doc.warehouse=get_obj(ctx,Warehouse,previous['warehouse']) if previous.get('warehouse') else None
    doc.location=doc.warehouse.location if doc.warehouse else get_obj(ctx,Location,previous['location']) if previous.get('location') else None
    if previous.get('date'):doc.date=date.fromisoformat(str(previous['date']))
    doc.party=next((get_obj(ctx,Party,previous[key]) for key in ('party','supplier','customer') if previous.get(key)),None)
    doc.employee=get_obj(ctx,Employee,previous['employee']) if previous.get('employee') else None
    doc.save(update_fields=['data','date','party','employee','product_lines','warehouse','location'])
    AuditEvent.objects.create(business=ctx.business,user=ctx.user,action='draft.undo',target=str(doc.pk),details={'source_event':event.pk,'financial_effect':False})
    return view(ctx,doc.pk)
