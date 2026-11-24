import base64,io
from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import DatabaseError,transaction
from django.core.files.uploadedfile import SimpleUploadedFile
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env
from erp.models import Document,Entry,StockMovement,Business,Location,Membership
from erp.core import Context,execute,balance
from erp.capture_models import DocumentCapture,CaptureReview
from erp import capture

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6J18AAAAASUVORK5CYII=')

@pytest.fixture
def capture_env(growth_env,monkeypatch):
    ctx,post,wh,*_=growth_env
    monkeypatch.setattr(capture,'extract',lambda raw,name:('image/png',{'text':'INVOICE\nInvoice No: TEST-103\nDate: 2026-06-01\nTOTAL AFN 120.00','preview':base64.b64encode(PNG).decode(),'method':'controlled_fixture','pages':1,'languages':['eng','fas'],'human_review_required':True}))
    def imported(raw=PNG,**kwargs):
        return post('capture_import',{'location':wh.location_id,'filename':'receipt.png','source_content':base64.b64encode(raw).decode(),**kwargs})
    def reviewed(doc,**kwargs):
        return post('capture_review',{'capture':doc.result['capture'],'kind':'expense_post','invoice_date':'2026-06-01','amount':'120','expense_account':'EXPENSE','line':'shared','cash_account':'CASH','human_confirmed':True,'reason':'Compared original source and corrected details.',**kwargs})
    return (*growth_env,imported,reviewed)

def test_local_image_and_pdf_engines_extract_real_evidence_without_network(tmp_path):
    from PIL import Image,ImageDraw,ImageFont
    assert capture.tools()['ready'],'Install the documented private local OCR engines before acceptance testing.'
    image=Image.new('RGB',(1500,600),'white');draw=ImageDraw.Draw(image);font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',48)
    draw.multiline_text((70,70),'INVOICE\nInvoice No: LOCAL-902\nDate: 2026-06-01\nTOTAL AFN 120.00',font=font,fill='black',spacing=18)
    out=io.BytesIO();image.save(out,format='PNG');media,result=capture.extract(out.getvalue(),'local.png')
    assert media=='image/png' and result['method']=='tesseract' and '120.00' in result['text']
    assert capture.suggestions(result['text'])['amount']=='120.00' and result['preview']
    pdf=io.BytesIO();image.save(pdf,format='PDF');media,result=capture.extract(pdf.getvalue(),'scan.pdf')
    assert media=='application/pdf' and result['method']=='pdf_tesseract' and '120.00' in result['text']

def test_suggestions_do_not_guess_unknown_ambiguous_dates_accounts_or_currency():
    value=capture.suggestions('Total 120\nGrand Total 125\nDate 01/02/2026\nInvoice No: A-2')
    assert value['amount'] is None and value['invoice_date'] is None and value['account'] is None and value['supplier'] is None
    assert capture.suggestions('TOTAL AFN ۱۲۰٫۰۰\nDate: 2026-06-01')['amount']=='120.00'
    assert capture.suggestions('TOTAL USD 120')['currency']=='unsupported'

def test_import_review_and_one_final_post_keep_original_and_do_not_double_cash(capture_env):
    ctx,post,wh,sp,raw,customer,supplier,imported,reviewed=capture_env
    post('opening_cash',{'location':wh.location_id,'amount':'1000','reason':'Synthetic reviewed opening for OCR acceptance.'})
    initial=(Entry.objects.count(),StockMovement.objects.count())
    source=imported();item=DocumentCapture.objects.get(pk=source.result['capture'])
    assert bytes(item.original)==PNG and item.extracted_text and 'source_content' not in source.data
    assert initial==(Entry.objects.count(),StockMovement.objects.count())
    review=reviewed(source);draft=Document.objects.get(pk=review.result['draft']);assert draft.state=='draft' and draft.amount==120
    assert initial==(Entry.objects.count(),StockMovement.objects.count())
    capture.validate_draft_source(ctx,draft)
    posted=execute(ctx,draft.kind,draft.data,'capture-final-key');assert balance(ctx,'CASH',location=wh.location_id)==880
    assert CaptureReview.objects.get(capture=item).posted_document_id==posted.pk
    assert execute(ctx,draft.kind,draft.data,'capture-final-key').pk==posted.pk
    with pytest.raises(ValidationError):execute(ctx,draft.kind,draft.data,'capture-another-key')
    with pytest.raises(ValidationError):reviewed(source)
    assert balance(ctx,'CASH',location=wh.location_id)==880

def test_hash_and_supplier_reference_duplicates_are_blocked(capture_env):
    ctx,post,wh,sp,raw,customer,supplier,imported,reviewed=capture_env
    source=imported()
    with pytest.raises(ValidationError):imported()
    reviewed(source,supplier=supplier.pk,supplier_reference='AB-123',cash_account='')
    second=imported(raw=PNG+b'other-original')
    with pytest.raises(ValidationError):reviewed(second,supplier=supplier.pk,supplier_reference=' ab-123 ',cash_account='')
    assert CaptureReview.objects.count()==1 and not Entry.objects.exists()

def test_missing_confirmation_unsupported_amount_currency_and_accounts_roll_back(capture_env):
    ctx,post,wh,sp,raw,customer,supplier,imported,reviewed=capture_env;source=imported()
    for changes in [{'human_confirmed':False},{'amount':'120.001'},{'amount':'-1'},{'expense_account':'SALARY'},{'expense_account':'RAW'}]:
        with pytest.raises((ValidationError,PermissionDenied)):reviewed(source,**changes)
    assert not CaptureReview.objects.exists() and not Entry.objects.exists()
    rejected=post('capture_reject',{'capture':source.result['capture'],'reason':'Unreadable original; staff will retake the document.'})
    assert rejected.result['state']=='rejected' and DocumentCapture.objects.count()==1
    with pytest.raises(ValidationError):reviewed(source)

def test_partial_receipt_or_price_change_cannot_be_invented_by_scan(capture_env):
    ctx,post,wh,sp,raw,customer,supplier,imported,reviewed=capture_env
    receipt=post('purchase_receive',{'warehouse':wh.pk,'supplier':supplier.pk,'bill_now':False,'lines':[{'product':raw.pk,'quantity':'10','unit_cost':'12'}]})
    source=imported()
    with pytest.raises(ValidationError):reviewed(source,kind='purchase_bill',receipt=receipt.pk,supplier=supplier.pk,amount='125')
    before=Entry.objects.count();review=reviewed(source,kind='purchase_bill',receipt=receipt.pk,supplier=supplier.pk,supplier_reference='SUP-01')
    draft=Document.objects.get(pk=review.result['draft']);assert Entry.objects.count()==before and draft.product_lines==['sponge']
    final=execute(ctx,'purchase_bill',draft.data,'scanned-goods-bill');assert final.amount==120
    assert balance(ctx,'AP',party=supplier.pk)==-120 and balance(ctx,'GRNI')==0

def test_source_tenant_scope_sensitive_permissions_and_private_json(capture_env):
    ctx,post,wh,sp,raw,customer,supplier,imported,reviewed=capture_env;source=imported();item=DocumentCapture.objects.get(pk=source.result['capture'])
    client=client_for(ctx.user,ctx.business)
    assert client.get(f'/api/captures/detail/?id={item.pk}').status_code==200
    assert b'120.00' in client.get(f'/api/captures/detail/?id={item.pk}').content
    assert b'INVOICE' not in client.get(f'/api/documents/{source.pk}/').content
    ctx.membership.permissions=['capture.view','capture.upload','finance.view','inventory.raw','cost.view'];ctx.membership.save()
    for route in [f'/api/captures/detail/?id={item.pk}',f'/api/captures/source/?id={item.pk}',f'/api/captures/preview/?id={item.pk}',f'/api/documents/{source.pk}/',f'/api/documents/{source.pk}/print/']:
        assert client.get(route).status_code==403,route
    ctx.membership.permissions=['*'];ctx.membership.save()
    other=Business.objects.create(name='Other source owner',slug='other-source-owner');foreign=Location.objects.create(business=other,code='X',name='Other source location')
    with pytest.raises(DatabaseError),transaction.atomic():DocumentCapture.objects.filter(pk=item.pk).update(location=foreign)
    with pytest.raises(ValidationError):capture.capture_for(Context(ctx.user,other,Membership.objects.create(business=other,user=ctx.user,permissions=['*'],all_locations=True,product_lines=['sponge','adhesive','shared'])),item.pk)

def test_immutable_source_review_and_altered_draft_cannot_post(capture_env):
    ctx,post,wh,sp,raw,customer,supplier,imported,reviewed=capture_env;source=imported();review=reviewed(source);stored=CaptureReview.objects.get(pk=review.result['review']);draft=stored.draft
    with pytest.raises(DatabaseError),transaction.atomic():DocumentCapture.objects.filter(pk=stored.capture_id).update(extracted_text='changed')
    with pytest.raises(DatabaseError),transaction.atomic():CaptureReview.objects.filter(pk=stored.pk).update(reason='changed')
    altered={**draft.data,'amount':'1'}
    with pytest.raises(ValidationError):execute(ctx,draft.kind,altered,str(uuid4()))
    draft.data=altered;draft.save(update_fields=['data'])
    with pytest.raises(ValidationError):capture.validate_draft_source(ctx,draft)
    assert not Entry.objects.exists() and stored.posted_document_id is None

def test_missing_engine_invalid_mime_and_oversize_are_explicit(monkeypatch):
    monkeypatch.setattr(capture,'tools',lambda:{'ready':False})
    with pytest.raises(ValidationError,match='not configured'):capture.extract(PNG,'source.png')
    with pytest.raises(ValidationError,match='matching extension'):capture.extract(PNG,'source.pdf')
    with pytest.raises(ValidationError):capture.extract(b'x'*(capture.MAX_FILE+1),'source.png')
