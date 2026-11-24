from decimal import Decimal
import pytest
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.test import Client
from erp.models import Business, Membership, Location, Warehouse, Product, Document, Account, Entry, Attachment, BOM
from erp.seed import bootstrap
from erp.core import Context, execute, json_value

@pytest.fixture
def environment(db):
    user=User.objects.create_user(username='apitest',password='Long-synthetic-password83')
    business=bootstrap(Business.objects.create(name='Test business',slug='api-test'))
    membership=Membership.objects.create(user=user,business=business,permissions=['*'],all_locations=True,product_lines=['sponge','adhesive','shared'])
    loc=Location.objects.create(business=business,name='Herat',code='H')
    warehouse=Warehouse.objects.create(business=business,location=loc,name='Main')
    product=Product.objects.create(business=business,code='SP45',name='اسفنج 45 کیلو گرام',price=Decimal('500'),unit='cm')
    return user,business,membership,loc,warehouse,product

def client_for(user,business):
    client=Client(); client.force_login(user)
    client.defaults['HTTP_X_BUSINESS_ID']=str(business.pk)
    client.defaults['HTTP_ACCEPT_LANGUAGE']='en'
    return client

def test_session_requires_csrf_and_rejects_invalid_password(environment):
    user,business,*_=environment
    client=Client(enforce_csrf_checks=True)
    session=client.get('/api/session/')
    assert session.status_code==200 and session.json()['user'] is None
    assert client.post('/api/session/',{'username':user.username,'password':'Long-synthetic-password83'},content_type='application/json').status_code==403
    token=session.json()['csrfToken']
    success=client.post('/api/session/',{'username':user.username,'password':'Long-synthetic-password83'},content_type='application/json',HTTP_X_CSRFTOKEN=token)
    assert success.status_code==200 and success.json()['user']['username']==user.username

def test_business_and_nested_foreign_key_isolation(environment):
    user,business,membership,loc,warehouse,product=environment
    other=Business.objects.create(name='Furniture',slug='private-furniture')
    foreign=Location.objects.create(business=other,name='Private location',code='P')
    client=client_for(user,business)
    assert client.get('/api/catalog/',HTTP_X_BUSINESS_ID=str(other.pk)).status_code==403
    result=client.post('/api/catalog/warehouses/',{'location':foreign.pk,'name':'Wrong tenant','kind':'store'},content_type='application/json')
    assert result.status_code==400
    with pytest.raises(DatabaseError),transaction.atomic():
        Warehouse.objects.create(business=business,location=foreign,name='Direct wrong tenant')

def test_cut_sale_api_exact_balances_and_idempotency(environment):
    user,business,membership,loc,warehouse,product=environment
    ctx=Context(user,business)
    opening=execute(ctx,'stock_opening',{'warehouse':warehouse.pk,'lines':[{'product':product.pk,'value':'10000','blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'1000'}]}]},'open')
    from erp.models import Block
    block=Block.objects.get(business=business)
    payload={'warehouse':warehouse.pk,'customer_name':'Walk-in','phone':'0700000000','lines':[{'product':product.pk,'block':block.pk,'thickness_mm':'22','sheet_count':1}],'paid':'500'}
    client=client_for(user,business)
    first=client.post('/api/operations/sale/',payload,content_type='application/json',HTTP_IDEMPOTENCY_KEY='sale-key')
    assert first.status_code==201,first.content
    assert first.json()['document']['amount']=='1100.00'
    assert first.json()['document']['balance']=='600.00'
    block.refresh_from_db(); assert block.remaining_height_mm==Decimal('978')
    second=client.post('/api/operations/sale/',payload,content_type='application/json',HTTP_IDEMPOTENCY_KEY='sale-key')
    assert second.json()['document']['id']==first.json()['document']['id']
    block.refresh_from_db(); assert block.remaining_height_mm==Decimal('978')

def test_posted_entries_and_documents_protected_in_database(environment):
    user,business,membership,loc,warehouse,product=environment
    doc=execute(Context(user,business),'stock_opening',{'warehouse':warehouse.pk,'lines':[{'product':product.pk,'value':'10000','blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'1000'}]}]},'open')
    with pytest.raises(DatabaseError),transaction.atomic(): Document.objects.filter(pk=doc.pk).update(amount=Decimal('1'))
    with pytest.raises(DatabaseError),transaction.atomic(): Entry.objects.filter(document=doc).update(debit=Decimal('3'))
    with pytest.raises(DatabaseError),transaction.atomic(): Entry.objects.create(document=doc,account=Account.objects.get(business=business,code='EQUITY'),debit=Decimal('1'))

def test_sales_api_hides_costs_raw_materials_and_consumption(environment):
    user,business,membership,loc,warehouse,product=environment
    raw=Product.objects.create(business=business,code='SECRET',name='Confidential raw',kind='raw',line='shared',unit='kg')
    execute(Context(user,business),'stock_opening',{'warehouse':warehouse.pk,'lines':[{'product':raw.pk,'quantity':'100','value':'2000'}]},'rawopen')
    membership.permissions=['sales.view','sales.post','inventory.view']; membership.save()
    client=client_for(user,business)
    assert raw.pk not in [p['id'] for p in client.get('/api/catalog/').json()['products']]
    stock=client.get('/api/stock/').json()
    assert not stock['pools']
    from erp.api import redact
    public=redact(Context(user,business),{'wip_in':'2000','expected':{'product':raw.pk},'cost':'50','quantity':'2.2'})
    assert public=={'quantity':'2.2'}
    denied=client.post('/api/operations/sale/',{'warehouse':warehouse.pk,'lines':[{'product':raw.pk,'quantity':'1','unit_price':'0'}]},content_type='application/json',HTTP_IDEMPOTENCY_KEY='guessed-raw')
    assert denied.status_code==403

def test_mixed_lines_and_location_denial(environment):
    user,business,membership,loc,warehouse,product=environment
    doc=Document.objects.create(business=business,kind='sale',number='MIXED',date='2026-10-28',amount='5000',state='posted',product_lines=['sponge','adhesive'],location=loc,created_by=user,idempotency_key='mixed',request_hash='x')
    membership.permissions=['sales.view']; membership.product_lines=['sponge','shared']; membership.save()
    client=client_for(user,business)
    assert client.get(f'/api/documents/{doc.pk}/').status_code==403
    assert not client.get('/api/documents/').json()['results']

def test_throttle(environment):
    user,business,*_=environment
    client=Client()
    for _ in range(5): assert client.post('/api/session/',{'username':user.username,'password':'bad'},content_type='application/json').status_code==400
    assert client.post('/api/session/',{'username':user.username,'password':'bad'},content_type='application/json').status_code==429

def test_approval_limit_request_and_distinct_approver(environment):
    from erp.models import Party
    user,business,membership,loc,warehouse,product=environment
    membership.permissions=['finance.post','finance.view','finance.approve','drafts.create']; membership.approval_limit=Decimal('100'); membership.save()
    business.settings={'separate_approver':False};business.save()
    client=client_for(user,business)
    supplier=Party.objects.create(business=business,name='Test supplier',kind='supplier')
    payload={'amount':'500','expense_account':'EXPENSE','supplier':supplier.pk,'description':'Synthetic expense','location':loc.pk}
    result=client.post('/api/operations/expense_post/',payload,content_type='application/json',HTTP_IDEMPOTENCY_KEY='over-limit')
    # Explicit approval permission is independent of the ordinary posting limit.
    assert result.status_code==201,result.content
    business.settings={'separate_approver':True};business.save()
    assert client.post('/api/operations/expense_post/',payload,content_type='application/json',HTTP_IDEMPOTENCY_KEY='own-approval-denied').status_code==403
    membership.permissions=['finance.post','finance.view','drafts.create']; membership.save()
    result=client.post('/api/operations/expense_post/',payload,content_type='application/json',HTTP_IDEMPOTENCY_KEY='no-approval')
    assert result.status_code==403 and not Document.objects.filter(idempotency_key='no-approval').exists()
    request=client.post('/api/approvals/',{'kind':'expense_post','data':payload},content_type='application/json')
    assert request.status_code==201,request.json()
    approval=request.json()['document']['id']
    membership.permissions+=['finance.approve']; membership.save()
    assert client.post(f'/api/approvals/{approval}/',{},content_type='application/json').status_code==403
    reviewer=User.objects.create_user(username='reviewer',password='Safe-reviewer-password84')
    Membership.objects.create(user=reviewer,business=business,permissions=['*'],all_locations=True,product_lines=['sponge','adhesive','shared'])
    reviewed=client_for(reviewer,business).post(f'/api/approvals/{approval}/',{},content_type='application/json')
    assert reviewed.status_code==201,reviewed.content
    assert reviewed.json()['document']['amount']=='500.00'

def test_private_attachment_print_and_business_creation(environment,tmp_path,settings):
    from django.core.files.uploadedfile import SimpleUploadedFile
    settings.MEDIA_ROOT=tmp_path
    user,business,membership,loc,warehouse,product=environment
    doc=execute(Context(user,business),'opening_cash',{'location':loc.pk,'account':'CASH','amount':'1000','reason':'Reviewed opening'},'opening')
    client=client_for(user,business)
    uploaded=client.post('/api/attachments/',{'document':doc.pk,'file':SimpleUploadedFile('evidence.txt',b'Synthetic evidence')})
    assert uploaded.status_code==201,uploaded.content
    attachment=uploaded.json()['id']
    assert client.get(f'/api/attachments/{attachment}/').status_code==200
    assert client.get(f'/api/documents/{doc.pk}/print/').status_code==200
    other_user=User.objects.create_user(username='unassigned')
    assert client_for(other_user,business).get(f'/api/attachments/{attachment}/').status_code==403
    created=client.post('/api/businesses/',{'name':'Isolated new furniture','slug':'new-furniture','location_name':'Workshop'},content_type='application/json')
    assert created.status_code==201,created.content
    new_id=created.json()['id']
    catalog=client.get('/api/catalog/',HTTP_X_BUSINESS_ID=str(new_id)).json()
    assert catalog['products']==[] and catalog['parties']==[] and len(catalog['locations'])==1

def test_incoming_transfer_detail_for_kabul_receiver(environment):
    from erp.models import Block
    user,business,membership,loc,warehouse,product=environment
    kabul=Location.objects.create(business=business,name='Kabul',code='K')
    destination=Warehouse.objects.create(business=business,location=kabul,name='Kabul store')
    execute(Context(user,business),'stock_opening',{'warehouse':warehouse.pk,'lines':[{'product':product.pk,'value':'10000','blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'1000'}]}]},'open')
    transfer=execute(Context(user,business),'transfer_dispatch',{'warehouse':warehouse.pk,'destination':destination.pk,'lines':[{'product':product.pk,'block':Block.objects.get().pk,'quantity':'100'}]},'dispatch')
    receiver=User.objects.create_user(username='receiver')
    Membership.objects.create(user=receiver,business=business,permissions=['transfers.view','transfers.post','inventory.view'],location_ids=[kabul.pk],product_lines=['sponge','shared'])
    client=client_for(receiver,business)
    read=client.get(f'/api/documents/{transfer.pk}/')
    assert read.status_code==200,read.content
    assert 'cost' not in read.json()['result']['lines'][0]
    assert transfer.pk in [row['id'] for row in client.get('/api/documents/?kind=transfer_dispatch').json()['results']]

def test_used_product_units_and_account_classification_cannot_rewrite_history(environment):
    user,business,membership,loc,warehouse,product=environment
    execute(Context(user,business),'stock_opening',{'warehouse':warehouse.pk,'lines':[{'product':product.pk,'value':'10000','blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'1000'}]}]},'opening')
    client=client_for(user,business)
    wrong=client.patch(f'/api/catalog/products/{product.pk}/',{'unit':'kg'},content_type='application/json')
    assert wrong.status_code==400
    assert client.patch(f'/api/catalog/products/{product.pk}/',{'price':'550'},content_type='application/json').status_code==200
    used=Account.objects.get(business=business,code='FG')
    assert client.patch(f'/api/catalog/accounts/{used.pk}/',{'category':'expense'},content_type='application/json').status_code==400

def test_signed_allocation_and_ledger_reassignment_database_guards(environment):
    user,business,membership,loc,warehouse,product=environment
    doc=execute(Context(user,business),'opening_cash',{'location':loc.pk,'amount':'1000','reason':'Reviewed opening'},'cash')
    draft=Document.objects.create(business=business,kind='journal_adjust',number='DRAFT-GUARD',date=doc.date,created_by=user,idempotency_key='draftguard',request_hash='a'*64)
    row=Entry.objects.create(document=draft,account=Account.objects.get(business=business,code='EQUITY'),debit=Decimal('1'))
    with pytest.raises(DatabaseError),transaction.atomic(): Entry.objects.filter(pk=row.pk).update(document=doc)
    from erp.models import Allocation
    with pytest.raises(DatabaseError),transaction.atomic(): Allocation.objects.create(document=draft,invoice=doc,amount=Decimal('-1'))

def test_totp_enrollment_login_and_session_revocation(environment):
    from django_otp.plugins.otp_totp.models import TOTPDevice
    from django_otp.oath import TOTP
    from unittest.mock import patch
    import time
    user,business,*_=environment
    client=client_for(user,business)
    setup=client.post('/api/security/mfa_setup/',{},content_type='application/json')
    assert setup.status_code==200 and setup.json()['configuration_url'].startswith('otpauth://totp/')
    assert setup.json()['qr_data_url'].startswith('data:image/svg+xml;base64,')
    device=TOTPDevice.objects.get(user=user,confirmed=False)
    now=time.time()
    otp=TOTP(device.bin_key,device.step,device.t0,device.digits);otp.time=now
    with patch('django_otp.plugins.otp_totp.models.time.time',return_value=now):
        confirm=client.post('/api/security/mfa_confirm/',{'otp':str(otp.token()).zfill(device.digits)},content_type='application/json')
    assert confirm.status_code==200,confirm.content
    client.post('/api/logout/',{},content_type='application/json')
    assert client.post('/api/session/',{'username':user.username,'password':'Long-synthetic-password83'},content_type='application/json').status_code==400
    later=now+device.step*2;otp.time=later
    from datetime import datetime,timezone as datetime_timezone
    # Advance both TOTP time and its independent throttle clock; a slow/fast
    # machine must not make a valid-code test depend on a one-second real wait.
    with patch('django_otp.plugins.otp_totp.models.time.time',return_value=later),patch('django_otp.models.timezone.now',return_value=datetime.fromtimestamp(later,datetime_timezone.utc)):
        valid=client.post('/api/session/',{'username':user.username,'password':'Long-synthetic-password83','otp':str(otp.token()).zfill(device.digits)},content_type='application/json')
    assert valid.status_code==200,valid.content
    assert client.get('/api/context/').status_code==200
    assert client.post('/api/security/revoke_sessions/',{},content_type='application/json').status_code==200
    assert client.get('/api/context/').status_code==403

def test_import_preview_commit_retry_and_draft_has_no_ledger_effect(environment):
    from django.core.files.uploadedfile import SimpleUploadedFile
    user,business,membership,loc,warehouse,product=environment
    client=client_for(user,business)
    csv=b'code,name,kind,line,unit,price\nIMPORT-ONE,Synthetic material,raw,shared,kg,100\n'
    preview=client.post('/api/import/products/',{'file':SimpleUploadedFile('items.csv',csv),'preview':'true'})
    assert preview.status_code==200 and preview.json()['errors']==[]
    assert not Product.objects.filter(business=business,code='IMPORT-ONE').exists()
    for _ in range(2):
        committed=client.post('/api/import/products/',{'file':SimpleUploadedFile('items.csv',csv),'preview':'false'},HTTP_IDEMPOTENCY_KEY='same-import')
        assert committed.status_code==201,committed.content
    assert Product.objects.filter(business=business,code='IMPORT-ONE').count()==1
    before_entries=Entry.objects.count()
    draft=client.post('/api/documents/',{'kind':'sale','data':{'warehouse':warehouse.pk,'customer_name':'Deferred customer','lines':[{'product':product.pk,'quantity':'1'}]}},content_type='application/json')
    assert draft.status_code==201,draft.content
    assert draft.json()['state']=='draft' and Entry.objects.count()==before_entries

def test_exact_decimal_rejects_ambiguous_separator_and_accepts_local_numerals():
    from erp.core import D
    assert D('۱٬۵۰۰٫۲۵')==Decimal('1500.25')
    assert D('2.2')==Decimal('2.2')
    with pytest.raises(ValidationError): D('1,5')
    with pytest.raises(ValidationError): D(float('nan'))

def test_inventory_document_cannot_leak_cost_through_generic_total(environment):
    user,business,membership,loc,warehouse,product=environment
    doc=execute(Context(user,business),'stock_opening',{'warehouse':warehouse.pk,'lines':[{'product':product.pk,'value':'12345','blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'1000'}]}]},'private-cost')
    membership.permissions=['inventory.view'];membership.save()
    client=client_for(user,business)
    result=client.get(f'/api/documents/{doc.pk}/')
    assert result.status_code==200,result.content
    body=result.json()
    assert body['amount'] is None and 'total' not in body['result']
    assert 'cost' not in body['result']['lines'][0] and 'value' not in body['data']['lines'][0]
    assert body['result']['lines'][0]['quantity']=='100'

def test_employee_setup_effective_rate_and_review_checklist(environment):
    user,business,membership,loc,warehouse,product=environment
    client=client_for(user,business)
    created=client.post('/api/catalog/employees/',{'name':'Hourly part timer','location':loc.pk,'kind':'part_time','rate':'150','effective_date':'2026-01-01','advance_limit':'1000','terms':{'rate_basis':'hour'}},content_type='application/json')
    assert created.status_code==201,created.content
    employee=created.json()['id']
    unchanged=client.patch(f'/api/catalog/employees/{employee}/',{'name':'Updated worker name','rate':'150.000000'},content_type='application/json')
    assert unchanged.status_code==200,unchanged.content
    rate=client.patch(f'/api/catalog/employees/{employee}/',{'rate':'175','effective_date':'2026-02-01'},content_type='application/json')
    assert rate.status_code==200 and len(rate.json()['terms']['rates'])==2
    setup=client.get('/api/setup/')
    assert setup.status_code==200 and not next(item for item in setup.json()['items'] if item['key']=='opening')['ready']
    review=client.post('/api/setup/',{'area':'opening','reason':'Synthetic review fixture, not real-business sign-off'},content_type='application/json')
    assert review.status_code==200
    assert next(item for item in client.get('/api/setup/').json()['items'] if item['key']=='opening')['ready']

def test_bank_entry_picker_is_location_scoped(environment):
    user,business,membership,loc,warehouse,product=environment
    execute(Context(user,business),'opening_cash',{'location':loc.pk,'account':'BANK','amount':'5000','reason':'Verified opening'},'bankopen')
    client=client_for(user,business)
    query=client.get(f'/api/bank-entries/?location={loc.pk}&through_date=2099-12-31')
    assert query.status_code==200 and len(query.json()['results'])==1
    row=query.json()['results'][0]
    reconciled=client.post('/api/operations/bank_reconcile/',{'location':loc.pk,'account':'BANK','through_date':str(Document.objects.get(idempotency_key='bankopen').date),'statement_balance':'5000','entry_ids':[row['id']]},content_type='application/json',HTTP_IDEMPOTENCY_KEY='bank-clear')
    assert reconciled.status_code==201,reconciled.content
    assert reconciled.json()['result']['uncleared']=='0.00'

def test_malformed_line_payload_is_rejected_without_partial_document(environment):
    user,business,membership,loc,warehouse,product=environment
    client=client_for(user,business)
    result=client.post('/api/operations/production/',{'warehouse':warehouse.pk,'inputs':'not a list','outputs':[]},content_type='application/json',HTTP_IDEMPOTENCY_KEY='malformed-input')
    assert result.status_code==400
    assert not Document.objects.filter(business=business,idempotency_key='malformed-input').exists()
