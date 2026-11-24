"""Local OCR evidence, explicit human review and single ordinary-draft conversion."""
import base64,hashlib,json,os,re,shutil,subprocess,sys,tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from django.conf import settings
from django.core.exceptions import PermissionDenied,ValidationError
from django.db.models import Q
from .core import D,money,get_obj,account,json_value
from .models import Product,Location,Party,Document
from .capture_models import DocumentCapture,CaptureReview

MAX_FILE=5*1024*1024

def authorize(ctx,location=None):
    for permission in ['capture.view','finance.view','cost.view','inventory.raw','payroll.view']:ctx.require(permission)
    if not ctx.membership.all_locations:raise PermissionDenied('Source documents require complete business location scope.')
    if not ctx.has('documents.all_lines') and Product.objects.filter(business=ctx.business).exclude(line__in=ctx.membership.product_lines).exists():raise PermissionDenied('Source documents require complete business product scope.')
    if location:return get_obj(ctx,Location,location)

def capture_for(ctx,identifier):
    item=get_obj(ctx,DocumentCapture,identifier);authorize(ctx,item.location_id);return item

def tools():
    root=Path(settings.ROOT_DIR)
    local=root/'.local/tools/tesseract'
    default_pdf=root/'.local/tools/poppler/Library/bin'
    def executable(key,name,default):
        configured=os.environ.get(key,'').strip()
        path=Path(configured or (str(default) if Path(default).is_file() else shutil.which(name) or default))
        return str(path.resolve()) if path.is_file() else None
    tesseract=executable('ERP_TESSERACT_PATH','tesseract',local/'tesseract.exe')
    tessdata=Path(os.environ.get('ERP_TESSDATA_DIRECTORY',str(local/'tessdata'))).resolve()
    pdftotext=executable('ERP_PDFTOTEXT_PATH','pdftotext',default_pdf/'pdftotext.exe')
    pdftoppm=executable('ERP_PDFTOPPM_PATH','pdftoppm',default_pdf/'pdftoppm.exe')
    ready=bool(tesseract and pdftoppm and all((tessdata/(lang+'.traineddata')).is_file() for lang in ['eng','fas']))
    return {'ready':ready,'tesseract':tesseract,'tessdata':str(tessdata),'pdftotext':pdftotext,'pdftoppm':pdftoppm}

def extract(raw,filename):
    if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_FILE:raise ValidationError('Choose one file no larger than5 MB.')
    suffix=Path(filename).suffix.lower()
    if raw.startswith(b'%PDF-') and suffix=='.pdf':kind='pdf';media='application/pdf'
    elif (raw.startswith(b'\x89PNG\r\n\x1a\n') and suffix=='.png') or (raw.startswith(b'\xff\xd8\xff') and suffix in {'.jpg','.jpeg'}):kind='image';media='image/png' if suffix=='.png' else 'image/jpeg'
    else:raise ValidationError('The original must be a valid PNG, JPEG or PDF with a matching extension.')
    config=tools()
    if not config['ready']:raise ValidationError('Local OCR is not configured. Install the local Tesseract eng+fas and Poppler engines; no source was uploaded to an external service.')
    with tempfile.TemporaryDirectory(prefix='nawa-capture-') as folder:
        source=Path(folder)/('source'+suffix);source.write_bytes(raw)
        args=[sys.executable,str(Path(__file__).with_name('capture_extract.py')),'--input',str(source),'--kind',kind]
        for field in ['tesseract','tessdata','pdftoppm']:args+=['--'+field,config[field]]
        try:
            result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90,check=False,env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1'},creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode or len(result.stdout)>2500000:raise ValueError()
            value=json.loads(result.stdout.decode('utf-8'))
        except (OSError,ValueError,subprocess.TimeoutExpired):raise ValidationError('Local extraction failed or exceeded90 seconds. Split the document or retake the image.')
    if value.get('error'):raise ValidationError(value['error'])
    text=value.get('text','')
    if not text.strip() or len(text)>50000:raise ValidationError('No supported readable text was extracted.')
    return media,value

def suggestions(text):
    # Recognized labels only: ambiguity stays blank, never the largest number.
    normalized=text.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫٬','01234567890123456789.,'))
    amounts=re.findall(r'(?im)^\s*(?:grand\s+total|total|amount\s+due|مجموع\s*کل|مجموع|جمع\s*کل)\s*[:：]?\s*(?:AFN|؋|افغانی)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?:AFN|؋|افغانی)?\s*$',normalized)
    amount=None
    if len(set(amounts))==1:
        try:
            amount_value=D(amounts[0]);amount=format(money(amount_value),'f') if amount_value>0 else None
        except ValidationError:pass
    dates=re.findall(r'(?im)^\s*(?:date|invoice\s+date|تاریخ)\s*[:：]?\s*(20\d{2}-\d{2}-\d{2})\s*$',normalized)
    invoice_date=None
    if len(set(dates))==1:
        try:invoice_date=date.fromisoformat(dates[0]).isoformat()
        except ValueError:pass
    refs=re.findall(r'(?im)^\s*(?:invoice\s*(?:no\.?|number|#)|receipt\s*(?:no\.?|number|#)|شماره\s*(?:بل|رسید))\s*[:：]?\s*([\w/-]{1,80})\s*$',normalized)
    foreign=bool(re.search(r'\b(?:USD|PKR|EUR|US\$)\b',normalized,re.I))
    return {'amount':amount,'invoice_date':invoice_date,'supplier_reference':refs[0] if len(set(refs))==1 else '',
            'currency':'unsupported' if foreign else 'AFN' if re.search(r'\bAFN\b|؋|افغانی',normalized,re.I) else None,
            'supplier':None,'account':None,'confidence':'unverified','human_review_required':True}

def import_capture(ctx,p,doc):
    ctx.require('capture.upload');location=authorize(ctx,p.get('location'))
    if not location:raise ValidationError('Select the source location.')
    filename=Path(str(p.get('filename','')).replace('\\','/')).name[:200]
    try:raw=base64.b64decode(p.get('source_content',''),validate=True)
    except (ValueError,TypeError):raise ValidationError('Invalid source encoding.')
    if len(raw)>MAX_FILE:raise ValidationError('Source exceeds5 MB.')
    fingerprint=hashlib.sha256(raw).hexdigest()
    if DocumentCapture.objects.filter(business=ctx.business,sha256=fingerprint).exists():raise ValidationError('This exact original was already captured. Open its existing review; do not import another copy.')
    media,result=extract(raw,filename)
    item=DocumentCapture.objects.create(business=ctx.business,location=location,filename=filename,media_type=media,sha256=fingerprint,original=raw,preview=base64.b64decode(result['preview']),extracted_text=result['text'],suggestions=suggestions(result['text']),extraction={k:v for k,v in result.items() if k not in {'text','preview'}},source=doc)
    doc.location=location;doc.data.pop('source_content',None)
    return {'capture':item.pk,'filename':filename,'sha256':fingerprint,'state':'review','financial_entries_created':False}

def reference(value):return str(value or '').strip().translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789')).casefold()

def reviewed_payload(ctx,item,p):
    if p.get('human_confirmed') is not True:raise ValidationError('A person must compare the original and explicitly confirm the corrected details.')
    if item.suggestions.get('currency')=='unsupported':raise ValidationError('This source identifies foreign currency. Use the supported foreign monetary workflow; AFN capture conversion is blocked.')
    kind=p.get('kind')
    if kind not in {'expense_post','purchase_bill'}:raise ValidationError('Choose an expense or a bill linked to an actual goods receipt.')
    try:effective=date.fromisoformat(str(p.get('invoice_date')))
    except (ValueError,TypeError):raise ValidationError('Choose the reviewed invoice date.')
    amount=D(p.get('amount'))
    if amount<=0 or amount!=money(amount):raise ValidationError('The reviewed AFN amount must be positive with at most two decimals.')
    supplier=get_obj(ctx,Party,p['supplier']) if p.get('supplier') else None
    if supplier and supplier.kind!='supplier':raise ValidationError('Select a supplier account.')
    ref=reference(p.get('supplier_reference'))
    if len(ref)>150:raise ValidationError('Supplier reference exceeds150 characters.')
    if supplier and ref and (CaptureReview.objects.filter(business=ctx.business,supplier=supplier,supplier_reference=ref).exists() or Document.objects.filter(business=ctx.business,kind__in=['purchase_bill','expense_post'],state='posted',party=supplier,data__supplier_reference__iexact=ref).exists()):raise ValidationError('This supplier reference was already reviewed or posted; compare the existing original.')
    payload={'date':effective.isoformat(),'location':item.location_id,'currency':'AFN','supplier_reference':ref,'document_capture':item.pk}
    receipt=None
    if kind=='expense_post':
        ctx.require('finance.post')
        selected=account(ctx,p.get('expense_account',''))
        if selected.category!='expense' or selected.control or selected.code in {'SALARY','LABOR_CLEARING','COST_CLEARING','COGS','WASTE','DEPRECIATION','IMPAIRMENT','COMMISSION'}:raise ValidationError('Select an ordinary non-control operating expense; use dedicated payroll, stock and manufacturing flows for their costs.')
        line=p.get('line')
        if line not in {'sponge','adhesive','shared'} or not ctx.line_allowed(line):raise PermissionDenied('Choose an authorized product line.')
        payload.update({'amount':format(amount,'f'),'expense_account':selected.code,'line':line})
        if supplier:payload['supplier']=supplier.pk
        else:
            if p.get('cash_account') not in {'CASH','BANK'}:raise ValidationError('Choose actual CASH or BANK payment, or select an unpaid supplier.')
            payload['cash_account']=p['cash_account']
    else:
        ctx.require('purchases.post');ctx.require('purchases.view')
        from .api import doc_permission
        receipt=get_obj(ctx,Document,p.get('receipt'));doc_permission(ctx,receipt)
        if receipt.kind!='purchase_receive' or receipt.state!='posted' or receipt.result.get('clearing')!='GRNI':raise ValidationError('Select an actual received-not-invoiced goods receipt.')
        if receipt.location_id!=item.location_id or not supplier or receipt.party_id!=supplier.pk:raise ValidationError('The original receipt must have the reviewed location and supplier.')
        if effective<receipt.date:raise ValidationError('Invoice date cannot precede its goods receipt.')
        if Document.objects.filter(business=ctx.business,reference=receipt,kind__in=['purchase_bill','purchase_return'],state='posted').exists() or CaptureReview.objects.filter(business=ctx.business,outcome='draft',approved_data__receipt=receipt.pk).exists():raise ValidationError('This capture flow accepts one complete unbilled receipt. Use the ordinary bill flow for prior bills, returns or partial matching.')
        if amount!=money(receipt.amount):raise ValidationError('The reviewed total must equal the full original receipt value; price differences require the ordinary controlled workflow.')
        payload.update({'receipt':receipt.pk,'supplier':supplier.pk,'warehouse':receipt.warehouse_id})
    return kind,payload,supplier,ref,amount,receipt

def review_capture(ctx,p,doc):
    ctx.require('capture.review');item=capture_for(ctx,p.get('capture'))
    if CaptureReview.objects.filter(capture=item).exists():raise ValidationError('This original already has a terminal review. Open the linked draft or recorded rejection.')
    reason=str(p.get('reason') or '').strip()
    if not 8<=len(reason)<=2000:raise ValidationError('Record a review reason of8 to2,000 characters.')
    kind,payload,supplier,ref,amount,receipt=reviewed_payload(ctx,item,p)
    from .core import create_draft
    draft=create_draft(ctx,kind,payload,'capture-draft-'+str(item.pk));draft.amount=amount
    if receipt:
        draft.product_lines=list(receipt.product_lines);ctx.lines.update(receipt.product_lines)
    else:
        draft.product_lines=[payload['line']];ctx.lines.add(payload['line'])
    draft.party=supplier;draft.save(update_fields=['amount','product_lines','party'])
    review=CaptureReview.objects.create(business=ctx.business,capture=item,outcome='draft',reason=reason,approved_data=payload,supplier=supplier,supplier_reference=ref,draft=draft,source=doc)
    doc.reference=item.source;doc.location=item.location;doc.party=supplier
    return {'capture':item.pk,'review':review.pk,'draft':draft.pk,'state':'draft','financial_entries_created':False}

def reject_capture(ctx,p,doc):
    ctx.require('capture.review');item=capture_for(ctx,p.get('capture'))
    if CaptureReview.objects.filter(capture=item).exists():raise ValidationError('This original already has a terminal review.')
    reason=str(p.get('reason') or '').strip()
    if not 8<=len(reason)<=2000:raise ValidationError('Record why the source is rejected (8 to2,000 characters).')
    review=CaptureReview.objects.create(business=ctx.business,capture=item,outcome='rejected',reason=reason,source=doc)
    doc.reference=item.source;doc.location=item.location
    return {'capture':item.pk,'review':review.pk,'state':'rejected','financial_entries_created':False}

def validate_draft_source(ctx,draft):
    review=CaptureReview.objects.filter(draft=draft).select_related('capture').first()
    if review:
        capture_for(ctx,review.capture_id);ctx.require('capture.review')
        if draft.data!=review.approved_data:raise ValidationError('Captured draft differs from its reviewed original. Do not silently edit approved extraction fields; reject/review before conversion or use an ordinary documented correction.')
        if review.posted_document_id:raise ValidationError('This captured source already created its one posted transaction.')

def enrich_registry(operations):
    for kind in ['expense_post','purchase_bill']:
        permission,original=operations[kind]
        def wrapped(ctx,p,doc,handler=original,expected_kind=kind):
            review=None
            if p.get('document_capture'):
                item=capture_for(ctx,p['document_capture']);ctx.require('capture.review')
                review=CaptureReview.objects.select_for_update(of=('self',)).filter(capture=item,outcome='draft').select_related('draft').first()
                if not review or not review.draft or review.draft.kind!=expected_kind or review.approved_data!=json_value(p):raise ValidationError('Post the exact human-reviewed source draft, not an altered capture payload.')
                if review.posted_document_id:raise ValidationError('This captured original has already posted once.')
                if review.draft.state!='draft':raise ValidationError('The reviewed source draft is no longer eligible.')
            result=handler(ctx,p,doc)
            if review:
                review.posted_document=doc;review.save(update_fields=['posted_document'])
                result={**(result or {}),'document_capture':review.capture_id}
            return result
        operations[kind]=(permission,wrapped)
    return operations

def document_guard(ctx,doc):
    if doc.kind in OPERATIONS:
        authorize(ctx,doc.location_id)
    for review in CaptureReview.objects.filter(business=ctx.business).filter(Q(draft_id=doc.pk)|Q(posted_document_id=doc.pk)):
        capture_for(ctx,review.capture_id)
    if doc.data.get('document_capture'):capture_for(ctx,doc.data['document_capture'])

OPERATIONS={'capture_import':('capture.upload',import_capture),'capture_review':('capture.review',review_capture),'capture_reject':('capture.review',reject_capture)}
