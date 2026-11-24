"""Explicitly authorized outbox. Provider acceptance is not delivery confirmation."""
import json,os,re,urllib.request,urllib.error
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from .models import ReminderMessage,Membership,AuditEvent
from .core import Context,get_obj,outstanding
from .models import Document

def send_queued(limit=20):
    results=[]
    for ident in ReminderMessage.objects.filter(state='queued').order_by('id').values_list('id',flat=True)[:limit]:
        with transaction.atomic():
            item=ReminderMessage.objects.select_for_update().get(pk=ident)
            if item.state!='queued':continue
            member=Membership.objects.filter(business=item.business,user=item.authorized_by,active=True).first()
            try:
                if not item.authorized_by.is_active:raise PermissionDenied('The authorizing user is inactive.')
                ctx=Context(item.authorized_by,item.business,member)
                ctx.require('messaging.send');get_obj(ctx,Document,item.task.invoice_id)
            except Exception:
                item.state='blocked';item.last_error='Authorization was revoked or invoice is outside the sender scope.';item.save();results.append({'id':ident,'state':item.state});continue
            bill=item.task.invoice
            if item.task.state!='open' or outstanding(bill)<=0:
                item.state='cancelled';item.last_error='The follow-up is closed or its debt is settled.';item.save();results.append({'id':ident,'state':item.state});continue
            fresh=f'{item.business.name}\n{bill.number}\nباقی‌مانده / Outstanding: {outstanding(bill)} {item.business.currency}\nتاریخ وعده / Promised date: {item.task.due_date}'
            if item.body!=fresh:
                item.state='blocked';item.last_error='Balance, promise or business details changed; prepare a reviewed replacement.';item.save();results.append({'id':ident,'state':item.state});continue
            url=os.environ.get('ERP_MESSAGE_PROVIDER_URL','');token=os.environ.get('ERP_MESSAGE_PROVIDER_TOKEN','')
            if not url or not token:
                item.state='blocked';item.last_error='Message provider is not configured.';item.save();results.append({'id':ident,'state':item.state});continue
            if not url.startswith('https://') or not re.fullmatch(r'\+?[0-9][0-9 -]{6,24}',item.recipient):
                item.state='blocked';item.last_error='Provider requires HTTPS and a valid recipient phone.';item.save();continue
            item.attempts+=1
            request=urllib.request.Request(url,data=json.dumps({'channel':item.channel,'to':item.recipient,'body':item.body,'idempotency_key':f'nawa-message-{item.id}'}).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Idempotency-Key':f'nawa-message-{item.id}'},method='POST')
            try:
                with urllib.request.urlopen(request,timeout=15) as reply:
                    if reply.status not in (200,201,202):raise ValueError()
                    result=json.loads(reply.read(16384));reference=str(result.get('message_id',''))
                    if not reference or len(reference)>150:raise ValueError()
                item.state='accepted';item.provider_reference=reference;item.sent_at=timezone.now();item.last_error=''
            except Exception:
                # An ambiguous timeout is not automatically retried without the same provider key.
                item.state='failed';item.last_error='Provider acceptance could not be verified. Review provider status before retrying.'
            item.save();AuditEvent.objects.create(business=item.business,user=item.authorized_by,action='message:'+item.state,target=str(item.id),details={'channel':item.channel,'attempt':item.attempts})
            results.append({'id':ident,'state':item.state,'delivered':False})
    return results
