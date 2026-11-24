"""Business-scoped document appearance; previews never create ledger records."""
from types import SimpleNamespace
from django.core.exceptions import ValidationError
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.http import HttpResponse
from .api import Boundary,response
from .models import AuditEvent,Business
from .growth import validate_print_profile

DEFAULTS={'legal_name':'','address':'','phone':'','footer':'','payment_instructions':'','accent_color':'#078492','receipt_paper':'A4','show_signatures':True,'signature_left':'تهیه‌کننده / Prepared by','signature_right':'دریافت‌کننده / Received by','show_printed_at':True,'logo_data_url':'','document_language':'bilingual','document_templates':{},'printer_profiles':[]}
def profile_for(business):return {**DEFAULTS,**business.settings.get('print_profile',{})}
class PrintSettingsAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request);ctx.require('settings.manage')
        if request.query_params.get('preview')!='1':return response({'profile':profile_for(ctx.business)})
        profile=profile_for(ctx.business);compact=request.query_params.get('paper')=='80mm'
        doc=SimpleNamespace(number='PREVIEW — نمونه چاپ',kind='receipt',state='draft',employee_id=None,party=None,location=None,warehouse_id=None)
        view={'business':ctx.business,'doc':doc,'title':'نمونه رسید — ثبت واقعی نیست','english_title':'PRINT PREVIEW — NOT A TRANSACTION','display_date':timezone.localdate().isoformat(),'status_label':'نمونه / Preview','party_snapshot':{'name':'مشتری نمونه / Sample customer'},'compact':compact,'copy':False,'sections':[{'label':'اقلام نمونه / Sample items','show_values':True,'rows':[{'index':1,'name':'محصول نمونه / Sample item','quantity':'2.2','unit':'cm','rate':'500.00','amount':'1,100.00','block_count':None}]}],'notice':'این صفحه فقط برای بررسی چاپ است و فروش، موجودی یا حساب را تغییر نمی‌دهد. / Preview only; no stock or accounting effect.','is_receipt':True,'show_amount':True,'amount_display':'1,100.00','receipt_amount_label':'مبلغ نمونه / Sample amount','show_balance':True,'balance_display':'0.00','printed_at':timezone.localtime().strftime('%Y-%m-%d %H:%M'),'print_profile':profile}
        from .print_profiles import effective,FAMILIES
        from .print_copy import apply
        group=request.query_params.get('family','receipt')
        if group not in FAMILIES:raise ValidationError('Select valid document-specific templates.')
        doc.kind={'invoice':'sale','quotation':'quotation','order':'sales_order','receipt':'receipt','purchase_bill':'purchase_bill','payroll':'payroll_settle','transfer':'transfer_dispatch','other':'expense_post'}[group]
        from .document_print import TITLES
        fa,en=TITLES.get(doc.kind,('نمونه سند','Sample document'));view['title']='نمونه — '+fa;view['english_title']='PREVIEW — '+en;view['is_receipt']=group in {'receipt','payroll'}
        params=dict(request.query_params.items())
        if 'paper' in params:params['compact']='1' if params['paper']=='80mm' else '0'
        apply(view,effective(profile,doc.kind,params))
        result=HttpResponse(render_to_string('document.html',view),content_type='text/html; charset=utf-8')
        # Embed only this authorized, synthetic preview in our own Settings.
        # All other pages retain the installation's DENY clickjacking policy.
        result['X-Frame-Options']='SAMEORIGIN'
        result['Content-Security-Policy']="frame-ancestors 'self'"
        return result
    @transaction.atomic
    def patch(self,request):
        ctx=self.ctx(request);ctx.require('settings.manage');business=Business.objects.select_for_update().get(pk=ctx.business.pk)
        if request.data.get('expected')!=profile_for(business):raise ValidationError('Print settings changed. Reload before saving.')
        profile=validate_print_profile(request.data.get('profile'));before=profile_for(business)
        business.settings={**business.settings,'print_profile':profile};business.save(update_fields=['settings'])
        AuditEvent.objects.create(business=business,user=request.user,action='print.settings',details={'before':before,'after':profile})
        return response({'profile':profile_for(business)})

class DocumentPrintHistoryAPI(Boundary):
    def get(self,request,pk):
        from .models import Document
        from .core import get_obj
        from .api import doc_permission
        ctx=self.ctx(request);ctx.require('documents.print');doc=get_obj(ctx,Document,pk);doc_permission(ctx,doc)
        query=AuditEvent.objects.filter(business=ctx.business,action='document.print',target=str(doc.pk)).select_related('user').order_by('-pk')
        allow={'event','family','language','paper','margin_mm','printer_profile','copy','content_sha256','profile_sha256'}
        return response({'count':query.count(),'results':[{'id':event.pk,'generated_at':event.at,'actor':event.user.get_username() if event.user_id else '',**{key:value for key,value in event.details.items() if key in allow},'physical_print_confirmed':False} for event in query[:50]],'limit':50,'meaning':'Print views were generated. Physical printer or PDF-save completion is not confirmed.'})
