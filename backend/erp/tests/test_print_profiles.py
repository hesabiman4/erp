import base64
from io import BytesIO
from decimal import Decimal
import hashlib
import pytest
from PIL import Image
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env,open_block
from erp.models import Document,Entry,StockMovement,AuditEvent,Business,Membership
from erp.print_settings import profile_for

def logo():
    buf=BytesIO();Image.new('RGB',(80,40),'teal').save(buf,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()

def save(client,profile):
    current=client.get('/api/print-settings/').json()['profile']
    return client.patch('/api/print-settings/',{'expected':current,'profile':{**current,**profile}},content_type='application/json')

def sale(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;block=open_block(post,wh,sp)
    return post('sale',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':sp.pk,'block':block.pk,'thickness_mm':'22'}],'paid':'500'})

def test_logo_document_templates_language_printer_and_issue_hash_do_not_change_books(growth_env):
    ctx,*_=growth_env;invoice=sale(growth_env);client=client_for(ctx.user,ctx.business)
    before=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    changed=save(client,{'logo_data_url':logo(),'legal_name':'Training factory','document_language':'fa','document_templates':{'invoice':{'title_dari':'بل رسمی آموزشی','title_english':'Training invoice','title_pashto':'روزنیز بل','footer':'Invoice footer <script>not executable</script>'},'quotation':{'footer':'Quote footer only'}},'printer_profiles':[{'id':'desk-a4','name':'Accounting desk','paper':'A4','margin_mm':12,'hardware_note':'Device not selected'},{'id':'counter','name':'Counter paper','paper':'80mm','margin_mm':4}]})
    assert changed.status_code==200,changed.content
    printed=client.get(f'/api/documents/{invoice.pk}/print/?language=en&printer=desk-a4')
    assert printed.status_code==200,printed.content[:300]
    html=printed.content.decode();assert 'lang="en" dir="ltr"' in html and 'Training invoice' in html and 'data:image/png;base64,' in html and 'margin:12mm' in html
    assert '1,100.00' in html and '600.00' in html and 'Invoice footer &lt;script&gt;' in html and '<script>not executable' not in html and 'Quote footer only' not in html
    event=AuditEvent.objects.filter(business=ctx.business,action='document.print',target=str(invoice.pk)).latest('pk')
    assert event.details['content_sha256']==hashlib.sha256(printed.content).hexdigest() and event.details['family']=='invoice' and event.details['physical_print_confirmed'] is False
    history=client.get(f'/api/documents/{invoice.pk}/print-history/').json()
    assert history['count']==1 and history['results'][0]['paper']=='A4' and not history['results'][0]['physical_print_confirmed']
    assert before==(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    invoice.refresh_from_db();assert invoice.amount==1100 and invoice.result['outstanding']=='600.00'
    pashto=client.get(f'/api/documents/{invoice.pk}/print/?language=ps&printer=counter').content.decode()
    assert 'lang="ps-AF" dir="rtl"' in pashto and 'روزنیز بل' in pashto and 'د سند نېټه' in pashto and '80mm 297mm' in pashto and '1,100.00' in pashto

@pytest.mark.parametrize('change',[
 {'logo_data_url':'https://outside.example/track.png'},
 {'logo_data_url':'data:image/svg+xml;base64,PHN2Zz4='},
 {'logo_data_url':'data:image/png;base64,not-an-image'},
 {'logo_data_url':False},
 {'document_language':[]},
 {'document_language':'unknown'},
 {'document_templates':{'invoice':{'hide_total':True}}},
 {'document_templates':{'invoice':{'title_dari':'x'*151}}},
 {'document_templates':{'invoice':{'paper':[]}}},
 {'printer_profiles':[{'id':'x','name':'Bad','paper':'A4','margin_mm':True}]},
 {'printer_profiles':[{'id':'x','name':'Bad','paper':'A4','margin_mm':100}]},
 {'printer_profiles':[{'id':'x','name':'Bad','paper':{},'margin_mm':4}]},
 {'printer_profiles':[{'id':'x','name':'A','paper':'A4','margin_mm':4},{'id':'x','name':'B','paper':'A4','margin_mm':4}]},
])
def test_unsafe_or_financial_template_options_are_rejected_atomically(growth_env,change):
    ctx,*_=growth_env;client=client_for(ctx.user,ctx.business);before=client.get('/api/print-settings/').json()['profile']
    response=save(client,change);assert response.status_code==400,response.content
    assert client.get('/api/print-settings/').json()['profile']==before

def test_history_and_print_profiles_enforce_document_business_and_action_scope(growth_env):
    ctx,*_=growth_env;invoice=sale(growth_env);client=client_for(ctx.user,ctx.business)
    before=AuditEvent.objects.filter(action='document.print').count()
    for query in ['language=invalid','printer=another-business-profile','compact=invalid']:
        assert client.get(f'/api/documents/{invoice.pk}/print/?{query}').status_code==400
    assert before==AuditEvent.objects.filter(action='document.print').count()
    AuditEvent.objects.create(business=ctx.business,user=ctx.user,action='document.print',target=str(invoice.pk),details={'private':'DO_NOT_DISCLOSE','content_sha256':'0'*64})
    assert 'DO_NOT_DISCLOSE' not in client.get(f'/api/documents/{invoice.pk}/print-history/').content.decode()
    other=Business.objects.create(name='Hidden furniture',slug='print-profile-private');Membership.objects.create(user=ctx.user,business=other,permissions=['*'],all_locations=True)
    assert client_for(ctx.user,other).get(f'/api/documents/{invoice.pk}/print-history/').status_code==400
    ctx.membership.permissions=['sales.view'];ctx.membership.save()
    assert client.get(f'/api/documents/{invoice.pk}/print-history/').status_code==403
    assert client.patch('/api/print-settings/',{},content_type='application/json').status_code==403

def test_preview_uses_selected_document_family_and_never_issues_a_document(growth_env):
    ctx,*_=growth_env;client=client_for(ctx.user,ctx.business)
    saved=save(client,{'document_templates':{'quotation':{'title_english':'Training quotation only','footer':'Quote conditions'}}})
    assert saved.status_code==200
    before=(Document.objects.count(),Entry.objects.count(),AuditEvent.objects.filter(action='document.print').count())
    preview=client.get('/api/print-settings/?preview=1&family=quotation&language=en&paper=A4')
    assert preview.status_code==200 and 'Training quotation only' in preview.content.decode() and 'Quote conditions' in preview.content.decode()
    assert before==(Document.objects.count(),Entry.objects.count(),AuditEvent.objects.filter(action='document.print').count())
