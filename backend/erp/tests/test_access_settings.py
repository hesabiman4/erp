"""PostgreSQL access administration and print settings boundaries."""
from copy import deepcopy
import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError,transaction
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env,open_block
from erp.models import AccessRole,Membership,AuditEvent,Document,Entry,Business,Location
from erp.access_control import permission_catalog
from erp.core import Context,registry


def member_snapshot(client,pk):
    return next({k:v for k,v in m.items() if k not in ('username','display_name')} for m in client.get('/api/access-control/').json()['members'] if m['id']==pk)

def role(client,name='Sales viewer',permissions=None,**extra):
    return client.post('/api/access-control/',{'action':'role','name':name,'permissions':permissions or ['sales.view'],**extra},content_type='application/json')

def worker(business,loc,permissions=None):
    user=User.objects.create_user(username='access-worker',password='SyntheticWorkerPass-93')
    return Membership.objects.create(user=user,business=business,permissions=permissions or ['sales.view'],location_ids=[loc.pk],product_lines=['sponge'],approval_limit='100')

def test_catalog_covers_all_registered_services_and_denies_nonadmins(environment):
    user,biz,owner,loc,*_=environment;c=client_for(user,biz);response=c.get('/api/access-control/');assert response.status_code==200
    codes={p['code'] for p in response.json()['permissions']};assert {p for p,_ in registry().values()}<=codes
    m=worker(biz,loc);assert client_for(m.user,biz).get('/api/access-control/').status_code==403
    assert not AccessRole.objects.exists()

def test_role_save_assign_cascade_stale_and_immediate_revocation(environment):
    user,biz,owner,loc,*_=environment;c=client_for(user,biz);m=worker(biz,loc)
    created=role(c,permissions=['sales.view','sales.post']);assert created.status_code==200,created.content;r=created.json()['role']
    assigned=c.post('/api/access-control/',{'action':'member','id':m.pk,'expected':member_snapshot(c,m.pk),'access_role':r['id']},content_type='application/json');assert assigned.status_code==200,assigned.content
    m.refresh_from_db();assert m.access_role_id==r['id'] and Context(m.user,biz).has('sales.post')
    updated=role(c,id=r['id'],version=r['version']);assert updated.status_code==200,updated.content;assert updated.json()['affected_members']==1
    assert not Context(m.user,biz).has('sales.post')
    assert client_for(m.user,biz).post('/api/operations/sale/',{},content_type='application/json',HTTP_IDEMPOTENCY_KEY='revoked-sale').status_code==403
    assert role(c,id=r['id'],version=r['version']).status_code==400
    assert AuditEvent.objects.filter(action='access.role',business=biz).count()==2

def test_role_and_assignment_cannot_cross_business(environment):
    user,biz,owner,loc,*_=environment;c=client_for(user,biz);other=Business.objects.create(name='Other',slug='other-access');foreign=AccessRole.objects.create(business=other,name='Private',permissions=['*']);m=worker(biz,loc)
    res=c.post('/api/access-control/',{'action':'member','id':m.pk,'expected':member_snapshot(c,m.pk),'access_role':foreign.pk},content_type='application/json');assert res.status_code==400
    assert role(c,id=foreign.pk,version=1).status_code==400
    m.refresh_from_db();assert m.access_role_id is None

def test_non_owner_cannot_escalate_roles_or_scopes(environment):
    user,biz,owner,loc,*_=environment;m=worker(biz,loc,['users.manage','sales.view']);c=client_for(m.user,biz)
    assert role(c,permissions=['*']).status_code==403
    assert role(c,permissions=['payroll.view']).status_code==403
    another=Location.objects.create(business=biz,name='Kabul',code='K')
    result=c.post('/api/access-control/',{'action':'member','id':m.pk,'expected':member_snapshot(c,m.pk),'permissions':['users.manage','sales.view'],'all_locations':True},content_type='application/json');assert result.status_code==403
    m.refresh_from_db();assert not m.all_locations

def test_last_owner_protected_on_new_and_legacy_routes(environment):
    user,biz,owner,*_=environment;c=client_for(user,biz)
    r=c.post('/api/access-control/',{'action':'member','id':owner.pk,'expected':member_snapshot(c,owner.pk),'permissions':['users.manage']},content_type='application/json');assert r.status_code==400
    r=c.patch(f'/api/catalog/memberships/{owner.pk}/',{'active':False},content_type='application/json');assert r.status_code==400
    owner.refresh_from_db();assert owner.active and owner.permissions==['*']

def test_stale_member_save_new_user_rollback_and_no_fake_permissions(environment):
    user,biz,owner,loc,*_=environment;c=client_for(user,biz);m=worker(biz,loc);old=member_snapshot(c,m.pk);m.approval_limit='150';m.save()
    r=c.post('/api/access-control/',{'action':'member','id':m.pk,'expected':old,'permissions':['sales.view']},content_type='application/json');assert r.status_code==400
    r=c.post('/api/access-control/',{'action':'member','username':'rolledback-user','password':'StrongSyntheticPassword-993','permissions':['imaginary.delete']},content_type='application/json');assert r.status_code==400;assert not User.objects.filter(username='rolledback-user').exists()

def test_print_settings_validation_scope_escaping_and_no_posting(environment):
    user,biz,owner,loc,*_=environment;c=client_for(user,biz);before=(Document.objects.count(),Entry.objects.count());profile=c.get('/api/print-settings/').json()['profile'];changed={**profile,'legal_name':'<script>alert(1)</script>','accent_color':'#123456','receipt_paper':'80mm','show_signatures':False,'show_printed_at':False}
    r=c.patch('/api/print-settings/',{'expected':profile,'profile':changed},content_type='application/json');assert r.status_code==200,r.content
    html=c.get('/api/print-settings/?preview=1&paper=80mm').content.decode();assert c.get('/api/print-settings/?preview=1')['X-Frame-Options']=='SAMEORIGIN'
    assert '80mm 297mm' in html and '#123456' in html and '&lt;script&gt;' in html and '<script>alert' not in html;assert '<section class="signatures">' not in html;assert 'PREVIEW' in html
    assert before==(Document.objects.count(),Entry.objects.count())
    assert c.patch('/api/print-settings/',{'expected':profile,'profile':changed},content_type='application/json').status_code==400
    for key,value in [('accent_color','red;display:none'),('show_signatures','false'),('receipt_paper','letter')]:
        bad={**changed,key:value};assert c.patch('/api/print-settings/',{'expected':changed,'profile':bad},content_type='application/json').status_code==400
    m=worker(biz,loc);assert client_for(m.user,biz).get('/api/print-settings/?preview=1').status_code==403

def test_receipt_default_paper_overrides_and_frozen_posting(growth_env):
    ctx,post,wh,sponge,raw,customer,*_=growth_env;block=open_block(post,wh,sponge)
    sale=post('sale',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':sponge.pk,'block':block.pk,'thickness_mm':'22'}],'paid':'0'})
    receipt=post('receipt',{'invoice':sale.pk,'location':wh.location_id,'amount':'100'});c=client_for(ctx.user,ctx.business);before=list(Entry.objects.values_list('id','debit','credit'));profile=c.get('/api/print-settings/').json()['profile']
    r=c.patch('/api/print-settings/',{'expected':profile,'profile':{**profile,'receipt_paper':'80mm','signature_left':'Reviewed <b>','signature_right':'Received'}},content_type='application/json');assert r.status_code==200
    html=c.get(f'/api/documents/{receipt.pk}/print/').content.decode();assert '80mm 297mm' in html and 'Reviewed &lt;b&gt;' in html
    assert 'size:A4' in c.get(f'/api/documents/{receipt.pk}/print/?compact=0').content.decode()
    assert 'size:A4' in c.get(f'/api/documents/{sale.pk}/print/').content.decode()
    assert before==list(Entry.objects.values_list('id','debit','credit'))
