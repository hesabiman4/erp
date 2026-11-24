import base64
import io
import zipfile
from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import DatabaseError,transaction
from django.core.files.uploadedfile import SimpleUploadedFile
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env
from erp.core import Context,execute
from erp.models import Document,Entry,StockMovement,Location,Account,Business,Product
from erp.statement_models import StatementImport,StatementRow,StatementReview,StatementMatch
from erp.statement_imports import parse,day


def parameters(wh,**kwargs):
    return {'date':'2026-06-04','location':wh.location_id,'institution':'Synthetic bank','account_reference':'Account-A','source_type':'bank','currency':'AFN','starts':'2026-06-01','ends':'2026-06-03','opening_balance':'0','closing_balance':'100','filename':'statement.csv',**kwargs}


def imported(post,wh,content=b'date,reference,description,amount\n2026-06-01,A1,Deposit,100.00\n',**kwargs):
    return post('statement_import',{**parameters(wh,**kwargs),'source_content':base64.b64encode(content).decode()})


def xlsx(rows,formula=False):
    sheet='<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    for position,row in enumerate(rows,1):
        sheet+=f'<row r="{position}">'
        for index,value in enumerate(row):
            col=chr(65+index)
            sheet+=f'<c r="{col}{position}" t="inlineStr"><is><t>{value}</t></is>'+('<f>1+1</f>' if formula else '')+'</c>'
        sheet+='</row>'
    sheet+='</sheetData></worksheet>'
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as archive:
        archive.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Statement" sheetId="1" r:id="r1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr('xl/worksheets/sheet1.xml',sheet)
    return output.getvalue()


def test_csv_preview_preserves_exact_local_numbers_and_posts_nothing(growth_env):
    ctx,post,wh,*_=growth_env
    before=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    file='date,reference,description,amount\n۱۴۰۵-۰۳-۱۱,آ۱,واریز,۱۰۰٫۰۰\n'.encode('utf-8-sig')
    value=parse(ctx,{**parameters(wh),'date_calendar':'jalali'},file,'test.csv')
    assert value['valid'] and value['rows'][0]['date']==date(2026,6,1) and value['rows'][0]['amount']==100
    assert before==(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    with pytest.raises(ValidationError):parse(ctx,parameters(wh),b'date,description,amount\n2026-06-01,Deposit,100.001\n','test.csv')


def test_uploaded_commit_reparses_and_keeps_private_immutable_original(growth_env):
    ctx,post,wh,*_=growth_env;client=client_for(ctx.user,ctx.business)
    body={k:str(v) for k,v in parameters(wh).items() if k!='filename'}
    raw=b'date,reference,description,amount\n2026-06-01,A1,Deposit,100\n'
    before=Entry.objects.count()
    first=client.post('/api/statements/commit/',{**body,'file':SimpleUploadedFile('import.csv',raw)},HTTP_IDEMPOTENCY_KEY='same-file-once')
    assert first.status_code==201,first.content
    second=client.post('/api/statements/commit/',{**body,'file':SimpleUploadedFile('import.csv',raw)},HTTP_IDEMPOTENCY_KEY='same-file-once')
    assert second.status_code==201 and second.json()['result']['statement']==first.json()['result']['statement']
    doc=Document.objects.get(pk=first.json()['document']['id']);assert 'source_content' not in doc.data and b'ZGF0ZS' not in first.content
    statement=StatementImport.objects.get(source=doc);assert bytes(statement.original)==raw and Entry.objects.count()==before
    response=client.get(f'/api/statements/source/?id={statement.id}')
    assert b''.join(response.streaming_content)==raw and response['Cache-Control']=='private, no-store'
    with pytest.raises(DatabaseError),transaction.atomic():StatementImport.objects.filter(pk=statement.id).update(original=b'changed')


def test_duplicate_rows_across_files_and_within_file_are_rejected(growth_env):
    ctx,post,wh,*_=growth_env
    imported(post,wh)
    count=StatementImport.objects.count()
    with pytest.raises(ValidationError):imported(post,wh,b'date,reference,description,amount\n2026-06-01,A1,Deposit,100.00\n\n',filename='different.csv')
    with pytest.raises(ValidationError):imported(post,wh,b'date,reference,description,amount\n2026-06-01,A2,Deposit,100\n2026-06-01,A2,Deposit,100\n',closing_balance='200')
    assert StatementImport.objects.count()==count


def test_mapping_and_debit_credit_perspective_validate_complete_balance(growth_env):
    ctx,post,wh,*_=growth_env
    raw=b'When,Ref,Text,Out,In\n2026-06-01,R1,Fee,20,0\n2026-06-02,R2,Receipt,0,120\n'
    first=parse(ctx,parameters(wh),raw,'statement.csv');assert first['needs_mapping'] and not first['valid']
    parsed=parse(ctx,{**parameters(wh),'mapping':{'date':'When','reference':'Ref','description':'Text','debit':'Out','credit':'In'}},raw,'statement.csv')
    assert [r['amount'] for r in parsed['rows']]==[Decimal('-20'),Decimal('120')]
    with pytest.raises(ValidationError):parse(ctx,{**parameters(wh),'closing_balance':'101','mapping':parsed['mapping']},raw,'statement.csv')
    with pytest.raises(ValidationError):parse(ctx,{**parameters(wh),'mapping':{'date':'Missing'}},raw,'statement.csv')


def test_values_only_xlsx_and_excel_dates_work_without_executing_formulas(growth_env):
    ctx,post,wh,*_=growth_env
    rows=[['date','reference','description','amount'],['2026-06-01','X1','Deposit','100.00']]
    result=parse(ctx,parameters(wh),xlsx(rows),'statement.xlsx');assert result['valid'] and result['rows'][0]['amount']==100
    with pytest.raises(ValidationError):parse(ctx,parameters(wh),xlsx(rows,True),'statement.xlsx')
    assert day('46174',excel=True)==date(2026,6,1)
    with pytest.raises(ValidationError):day('60',excel=True)
    with pytest.raises(ValidationError):parse(ctx,parameters(wh),b'not-a-workbook','statement.xlsx')


def test_exact_review_reconcile_uses_existing_bank_without_journal(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env
    post('opening_cash',{'date':'2026-05-31','location':wh.location_id,'account':'BANK','amount':'1000','reason':'Synthetic prior bank balance'})
    fee=post('expense_post',{'date':'2026-06-01','location':wh.location_id,'cash_account':'BANK','amount':'200','expense_account':'EXPENSE'})
    deposit=post('opening_cash',{'date':'2026-06-02','location':wh.location_id,'account':'BANK','amount':'300','reason':'Synthetic posted deposit'})
    raw_file=b'date,reference,description,amount\n2026-06-01,F1,Bank fee,-200\n2026-06-02,D1,Deposit,300\n'
    statement=StatementImport.objects.get(source=imported(post,wh,raw_file,opening_balance='1000',closing_balance='1100'))
    before=Entry.objects.count()
    for row,document in zip(statement.rows.order_by('position'),[fee,deposit]):
        entry=Entry.objects.get(document=document,account__code='BANK')
        post('statement_review',{'date':'2026-06-04','row':row.id,'outcome':'match','entry':entry.id,'note':'Confirmed bank evidence against original posted record.'})
    result=post('statement_reconcile',{'date':'2026-06-04','statement':statement.id})
    bank=Document.objects.get(pk=result.result['bank_document'])
    assert bank.kind=='bank_reconcile' and bank.result['cleared_balance']=='1100.00' and Entry.objects.count()==before
    with pytest.raises(ValidationError):post('statement_review',{'date':'2026-06-05','row':statement.rows.first().id,'outcome':'unmatch','note':'Sealed history cannot change.'})


def test_matching_rejects_wrong_amount_duplicate_entry_and_retains_release_history(growth_env):
    ctx,post,wh,*_=growth_env
    doc=post('opening_cash',{'location':wh.location_id,'account':'BANK','amount':'100','reason':'Synthetic deposit'})
    entry=Entry.objects.get(document=doc,account__code='BANK')
    statement=StatementImport.objects.get(source=imported(post,wh,b'date,reference,description,amount\n2026-06-01,A1,Deposit,100\n2026-06-02,A2,Deposit,100\n',closing_balance='200'))
    row,other=list(statement.rows.order_by('position'))
    post('statement_review',{'date':'2026-06-04','row':row.id,'outcome':'match','entry':entry.id,'note':'First reviewed match.'})
    with pytest.raises(ValidationError):post('statement_review',{'date':'2026-06-04','row':other.id,'outcome':'match','entry':entry.id,'note':'An entry cannot be counted twice.'})
    release=post('statement_review',{'date':'2026-06-04','row':row.id,'outcome':'unmatch','note':'Wrong reference; retain correction evidence.'})
    assert StatementMatch.objects.get(row=row).released_by_id==release.id
    post('statement_review',{'date':'2026-06-04','row':other.id,'outcome':'match','entry':entry.id,'note':'Corrected original bank reference.'})
    assert StatementReview.objects.filter(row=row).count()==2
    with pytest.raises(ValidationError):post('statement_reconcile',{'date':'2026-06-04','statement':statement.id})


def test_every_period_entry_is_required_and_opening_difference_blocks(growth_env):
    ctx,post,wh,*_=growth_env
    first=post('opening_cash',{'location':wh.location_id,'account':'BANK','amount':'100','reason':'Synthetic deposit'})
    post('opening_cash',{'location':wh.location_id,'account':'BANK','amount':'20','reason':'Unmatched deposit'})
    post('expense_post',{'location':wh.location_id,'cash_account':'BANK','expense_account':'EXPENSE','amount':'20'})
    statement=StatementImport.objects.get(source=imported(post,wh));row=statement.rows.first()
    post('statement_review',{'date':'2026-06-04','row':row.id,'outcome':'match','entry':Entry.objects.get(document=first,account__code='BANK').id,'note':'Amount is matched but two offsetting ledger rows remain.'})
    with pytest.raises(ValidationError,match='Every posted BANK'):post('statement_reconcile',{'date':'2026-06-04','statement':statement.id})


def test_saraf_is_explicit_afn_evidence_not_a_fictitious_bank_reconciliation(growth_env):
    ctx,post,wh,*_=growth_env
    statement=StatementImport.objects.get(source=imported(post,wh,source_type='saraf'))
    post('statement_review',{'date':'2026-06-04','row':statement.rows.first().id,'outcome':'verified','note':'Reviewed against saraf signed paper; evidence only.'})
    assert Entry.objects.count()==0 and statement.account_id is None
    with pytest.raises(ValidationError):post('statement_reconcile',{'date':'2026-06-04','statement':statement.id})
    with pytest.raises(ValidationError):imported(post,wh,currency='USD')


def test_statement_source_json_print_and_download_require_full_payroll_and_product_scope(growth_env):
    ctx,post,wh,*_=growth_env
    doc=imported(post,wh);statement=StatementImport.objects.get(source=doc)
    ctx.membership.permissions=['finance.view','finance.statements','documents.view'];ctx.membership.save()
    client=client_for(ctx.user,ctx.business)
    for path in ['/api/statements/imports/',f'/api/statements/source/?id={statement.id}',f'/api/documents/{doc.id}/',f'/api/documents/{doc.id}/print/']:
        assert client.get(path).status_code==403,path
    ctx.membership.permissions=['finance.view','finance.statements','documents.view','payroll.view'];ctx.membership.product_lines=['sponge'];ctx.membership.save()
    Product.objects.create(business=ctx.business,code='RESTRICTED',name='Restricted adhesive',kind='finished',line='adhesive',unit='kg')
    assert client.get('/api/statements/imports/').status_code==403


def test_tenant_location_and_immutable_row_guards(growth_env):
    ctx,post,wh,*_=growth_env
    doc=imported(post,wh);statement=StatementImport.objects.get(source=doc);row=statement.rows.first()
    with pytest.raises(DatabaseError),transaction.atomic():StatementRow.objects.filter(pk=row.id).update(amount='999')
    other=Business.objects.create(name='Foreign',slug='statement-foreign')
    with pytest.raises(DatabaseError),transaction.atomic():StatementRow.objects.create(business=other,statement=statement,position=99,date='2026-06-01',description='Wrong tenant',amount='1',fingerprint='a'*64)
    location=Location.objects.create(business=ctx.business,name='Other branch',code='STAT-OTHER')
    ctx.membership.all_locations=False;ctx.membership.location_ids=[location.id];ctx.membership.save()
    assert client_for(ctx.user,ctx.business).get(f'/api/statements/detail/?id={statement.id}').status_code==403


def test_invalid_windows_dates_mapping_and_source_sizes_are_honest(growth_env):
    ctx,post,wh,*_=growth_env
    with pytest.raises(ValidationError):imported(post,wh,date='2026-06-02')
    with pytest.raises(ValidationError):parse(ctx,parameters(wh),b'date,description,amount\n2026-05-31,Outside,100\n','statement.csv')
    with pytest.raises(ValidationError):parse(ctx,parameters(wh),b'bad','statement.xls')
    with pytest.raises(ValidationError):parse(ctx,parameters(wh),b'x'*(2*1024*1024+1),'statement.csv')


def test_one_real_bank_identity_is_bound_per_location_pool(growth_env):
    ctx,post,wh,*_=growth_env
    imported(post,wh)
    with pytest.raises(ValidationError,match='already bound'):imported(post,wh,b'date,reference,description,amount\n2026-06-01,B1,Another account,100\n',account_reference='Account-B')
    with pytest.raises(ValidationError,match='already bound'):imported(post,wh,b'date,reference,description,amount\n2026-06-01,B2,Another bank,100\n',institution='Another bank')
    assert StatementImport.objects.count()==1
    evidence=imported(post,wh,b'date,reference,description,amount\n2026-06-01,S1,Saraf record,100\n',source_type='saraf',institution='Independent saraf',account_reference='Saraf-Account')
    assert evidence.result['source_type']=='saraf'
