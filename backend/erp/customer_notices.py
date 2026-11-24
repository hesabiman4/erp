"""Consent-based notifications with an honest provider handoff and reviewed status."""
import json,os,re,urllib.request
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction
from .core import Context,get_obj
from .models import CustomerNotice,Document,Membership,AuditEvent,ReminderMessage,MessageEvent

TEMPLATES={
 'fa-AF':{'order_received':'سفارش شما ثبت شده است؛ تاریخ تحویل پس از تأیید فابریکه اعلام می‌شود.','invoice_issued':'بل فروش شما صادر شده است.','delivery_received':'دریافت اجناس شما ثبت شده است.'},
 'ps-AF':{'order_received':'ستاسو فرمایش ثبت شو؛ د سپارلو نېټه به د فابریکې له تایید وروسته درته وویل شي.','invoice_issued':'ستاسو د پلور بل صادر شو.','delivery_received':'ستاسو د توکو ترلاسه کول ثبت شول.'},
 'en':{'order_received':'Your order is recorded. Delivery timing requires factory confirmation.','invoice_issued':'Your sales invoice has been issued.','delivery_received':'Receipt of your goods has been recorded.'},
}


def notice_document(ctx,ident):
    from .api import doc_permission
    doc=get_obj(ctx,Document,ident);doc_permission(ctx,doc)
    if doc.kind not in {'sales_order','sale'} or doc.state!='posted' or not doc.party_id or doc.party.kind!='customer':raise ValidationError('Choose a posted customer sales order or invoice.')
    return doc


def validate_event(ctx,doc,template):
    if template=='order_received':
        from .operations import _commercial_cancelled
        if doc.kind!='sales_order' or _commercial_cancelled(ctx,doc):raise ValidationError('Only a current sales order can receive this update.')
    elif template=='invoice_issued':
        if doc.kind!='sale':raise ValidationError('Use an issued sales invoice.')
    elif template=='delivery_received':
        from .models import DeliveryConfirmation
        if doc.kind!='sale' or not DeliveryConfirmation.objects.filter(invoice=doc).exists():raise ValidationError('Record the recipient confirmation before preparing this delivery update.')
    else:raise ValidationError('Choose an available notification template.')


def prepare(ctx,p,source):
    doc=notice_document(ctx,p['document']);language=p.get('language','fa-AF');template=p['template']
    if language not in TEMPLATES:raise ValidationError('Choose Afghan Dari, Pashto or English.')
    validate_event(ctx,doc,template)
    channel=p.get('channel','manual');recipient=str(p.get('recipient') or doc.party.phone or '').strip()
    if channel not in {'manual','sms','whatsapp'}:raise ValidationError('Choose a supported channel.')
    if channel!='manual' and (p.get('consent_confirmed') is not True or not re.fullmatch(r'\+?[0-9][0-9 -]{6,24}',recipient)):raise ValidationError('Confirm customer consent and an eligible phone number.')
    if CustomerNotice.objects.filter(business=ctx.business,document=doc,channel=channel,recipient=recipient,template=template,state__in=['queued','accepted','delivered']).exists():raise ValidationError('This update is already queued, accepted or delivered. Review the existing notice.')
    body=f'{ctx.business.name}\n{doc.number}\n{TEMPLATES[language][template]}'
    item=CustomerNotice.objects.create(business=ctx.business,document=doc,party=doc.party,channel=channel,recipient=recipient,language=language,template=template,body=body,authorized_by=ctx.user,source=source,state='prepared' if channel=='manual' else 'queued')
    source.reference=doc;source.party=doc.party;source.location=doc.location
    return {'notice':item.id,'document':doc.id,'state':item.state,'body':body,'delivered':False,'financial_posting':False}


def notice_for(ctx,ident):
    ctx.require('messaging.send');item=get_obj(ctx,CustomerNotice,ident);notice_document(ctx,item.document_id)
    return item


def record_status(ctx,p,doc):
    item=notice_for(ctx,p['notice']);state=p['state'];evidence=str(p.get('evidence','')).strip()
    if not evidence or len(evidence)>2000:raise ValidationError('Record the provider evidence or cancellation reason.')
    valid=(state in {'delivered','failed'} and item.state=='accepted') or (state=='cancelled' and item.state in {'queued','blocked','failed','prepared'})
    if not valid:raise ValidationError('This status transition is unavailable; provider acceptance is required before recording delivery.')
    reference=str(p.get('provider_reference',''))
    if state in {'delivered','failed'} and (not reference or reference!=item.provider_reference):raise ValidationError('Match the accepted provider reference exactly.')
    item.state=state;item.last_error='' if state=='delivered' else evidence[:250];item.save(update_fields=['state','last_error'])
    doc.reference=item.source;doc.party=item.party;doc.location=item.document.location
    return {'notice':item.id,'state':state,'evidence':evidence,'provider_reference':reference,'confirmation_method':'Staff review of provider evidence; no provider callback was verified.','financial_posting':False}


def retry(ctx,p,doc):
    item=notice_for(ctx,p['notice']);reason=str(p.get('reason','')).strip()
    if item.state not in {'blocked','failed'} or not reason or p.get('provider_checked') is not True or p.get('consent_confirmed') is not True:raise ValidationError('Review the provider status, current customer consent and retry reason before retrying a blocked/failed notice.')
    if item.provider_reference:raise ValidationError('Provider-accepted notices require a new reviewed message rather than an ambiguous automatic retry.')
    if CustomerNotice.objects.filter(business=ctx.business,document=item.document,channel=item.channel,recipient=item.recipient,template=item.template,state__in=['queued','accepted','delivered']).exclude(pk=item.id).exists():raise ValidationError('A replacement update is already queued, accepted or delivered; cancel this old attempt instead of sending twice.')
    validate_event(ctx,item.document,item.template)
    item.state='queued' # Preserve original authorization, rechecked by sender.
    item.last_error='';item.save(update_fields=['state','last_error'])
    doc.reference=item.source;doc.party=item.party;doc.location=item.document.location
    return {'notice':item.id,'state':'queued','provider_key':f'nawa-notice-{item.id}','reason':reason,'financial_posting':False}


def send_notices(limit=20):
    results=[]
    for ident in CustomerNotice.objects.filter(state='queued').order_by('id').values_list('id',flat=True)[:limit]:
        with transaction.atomic():
            item=CustomerNotice.objects.select_for_update().select_related('business','document','authorized_by','source').get(pk=ident)
            if item.state!='queued':continue
            try:
                if not item.authorized_by.is_active:raise PermissionDenied('The authorizing user is inactive.')
                ctx=Context(item.authorized_by,item.business);notice_for(ctx,item.id);validate_event(ctx,item.document,item.template)
            except (PermissionDenied,ValidationError):
                item.state='blocked';item.last_error='Authorization, source event or customer access requires review.'
            else:
                url=os.environ.get('ERP_MESSAGE_PROVIDER_URL','');token=os.environ.get('ERP_MESSAGE_PROVIDER_TOKEN','')
                if not url or not token:item.state='blocked';item.last_error='Message provider is not configured.'
                elif not url.startswith('https://'):item.state='blocked';item.last_error='The provider requires HTTPS.'
                else:
                    key=f'nawa-notice-{item.id}';item.attempts+=1
                    req=urllib.request.Request(url,data=json.dumps({'to':item.recipient,'channel':item.channel,'body':item.body,'idempotency_key':key}).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Idempotency-Key':key},method='POST')
                    try:
                        with urllib.request.urlopen(req,timeout=15) as reply:
                            value=json.loads(reply.read(16384));reference=str(value.get('message_id',''))
                            if reply.status not in (200,201,202) or not reference or len(reference)>150:raise ValueError()
                        item.state='accepted';item.provider_reference=reference;item.last_error=''
                    except Exception:item.state='failed';item.last_error='Provider acceptance is uncertain. Check its status before any retry; the provider key is retained.'
            item.save(update_fields=['state','attempts','provider_reference','last_error'])
            AuditEvent.objects.create(business=item.business,user=item.authorized_by,action='notice:'+item.state,target=str(item.id),details={'attempt':item.attempts})
            results.append({'notice':item.id,'state':item.state,'delivered':False})
    return results


OPERATIONS={'notice_prepare':('messaging.send',prepare),'notice_status':('messaging.send',record_status),'notice_retry':('messaging.send',retry)}
