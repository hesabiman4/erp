import base64,io
from django.core.exceptions import PermissionDenied,ValidationError
from django.http import FileResponse
from .api import Boundary,response,document_data
from .core import execute
from .models import Document,Party,Account
from .capture_models import DocumentCapture,CaptureReview
from .capture import authorize,capture_for,tools,MAX_FILE


def summary(item):
    review=getattr(item,'review',None)
    return {'id':item.pk,'number':item.source.number,'date':item.source.date,'location':item.location_id,'filename':item.filename,'sha256':item.sha256,
            'media_type':item.media_type,'method':item.extraction.get('method'),'pages':item.extraction.get('pages'),'state':review.outcome if review else 'review',
            'draft':review.draft_id if review else None,'posted_document':review.posted_document_id if review else None}


class CaptureAPI(Boundary):
    def get(self,request,section):
        ctx=self.ctx(request);authorize(ctx)
        if section=='status':
            config=tools()
            return response({'local_ready':config['ready'],'languages':['eng','fas'],'external_uploads':False,'limits':{'file_mb':5,'pdf_pages':5,'image_pixels':16000000,'text_characters':50000},'human_review_required':True})
        if section=='captures':
            query=DocumentCapture.objects.filter(business=ctx.business).select_related('source','review__source','review__draft').order_by('-id')
            if request.headers.get('X-Location-ID'):query=query.filter(location=authorize(ctx,request.headers['X-Location-ID']))
            try:offset=int(request.query_params.get('offset',0))
            except ValueError:raise ValidationError('Use an integer page offset.')
            if offset<0:raise ValidationError('Use a nonnegative page offset.')
            return response({'results':[summary(item) for item in query[offset:offset+40]],'count':query.count(),'next_offset':offset+40 if query.count()>offset+40 else None})
        item=capture_for(ctx,request.query_params.get('id'))
        if section=='preview':return FileResponse(io.BytesIO(bytes(item.preview)),content_type='image/jpeg')
        if section=='source':
            result=FileResponse(io.BytesIO(bytes(item.original)),as_attachment=True,filename=item.filename,content_type=item.media_type)
            result['X-Content-Type-Options']='nosniff';result['Content-Security-Policy']="sandbox; default-src 'none'";return result
        if section!='detail':raise ValidationError('Unknown capture section.')
        review=CaptureReview.objects.filter(capture=item).select_related('source').first()
        receipts=[]
        if ctx.has('purchases.post') and ctx.has('purchases.view'):
            from .api import doc_permission
            for source in Document.objects.filter(business=ctx.business,kind='purchase_receive',state='posted',location=item.location, result__clearing='GRNI').order_by('-id')[:100]:
                try:doc_permission(ctx,source)
                except (PermissionDenied,ValidationError):continue
                if source.party_id and not Document.objects.filter(business=ctx.business,reference=source,kind__in=['purchase_bill','purchase_return'],state='posted').exists() and not CaptureReview.objects.filter(business=ctx.business,outcome='draft',approved_data__receipt=source.pk).exists():
                    receipts.append({'id':source.pk,'number':source.number,'supplier':source.party_id,'amount':source.amount,'date':source.date})
        accounts=Account.objects.filter(business=ctx.business,category='expense',control=False).exclude(code__in=['SALARY','LABOR_CLEARING','COST_CLEARING','COGS','WASTE','DEPRECIATION','IMPAIRMENT','COMMISSION'])
        return response({'capture':summary(item),'extracted_text':item.extracted_text,'suggestions':item.suggestions,'extraction':item.extraction,
                         'review':{'outcome':review.outcome,'reason':review.reason,'approved_data':review.approved_data,'number':review.source.number,'date':review.source.date} if review else None,
                         'suppliers':list(Party.objects.filter(business=ctx.business,kind='supplier').order_by('name').values('id','name')),
                         'expense_accounts':list(accounts.order_by('code').values('code','name')),'eligible_receipts':receipts})

    def post(self,request,section):
        ctx=self.ctx(request);authorize(ctx);ctx.require('capture.upload')
        if section!='import':raise ValidationError('Use the local source import endpoint.')
        upload=request.FILES.get('file')
        if not upload or upload.size>MAX_FILE:raise ValidationError('Choose a PNG, JPEG or PDF no larger than5 MB.')
        raw=upload.read(MAX_FILE+1)
        if len(raw)>MAX_FILE:raise ValidationError('Source exceeds5 MB.')
        values={key:value for key,value in request.data.items() if key!='file'}
        doc=execute(ctx,'capture_import',{**values,'filename':upload.name,'source_content':base64.b64encode(raw).decode('ascii')},request.headers.get('Idempotency-Key'))
        return response({'document':document_data(ctx,doc),'result':doc.result},201)
