import importlib
from types import SimpleNamespace
import pytest
from django.apps import apps
from django.db import connection
from erp.models import Location,Warehouse,AuditEvent,Document,Entry,StockMovement
from erp.tests.test_api import environment,client_for


def test_separate_names_display_per_language_and_audit_changes(environment):
    user,business,*_=environment;client=client_for(user,business)
    created=client.post('/api/catalog/locations/',{'code':'F2','name_fa':'فابریکه دوم','name_en':'Second factory','name_ps':'دویمه فابریکه'},content_type='application/json')
    assert created.status_code==201,created.content
    location=Location.objects.get(pk=created.json()['id'])
    assert location.name=='فابریکه دوم' and location.name_en=='Second factory'
    for language,expected in [('fa','فابریکه دوم'),('ps','دویمه فابریکه'),('en','Second factory')]:
        row=next(row for row in client.get('/api/catalog/locations/',HTTP_ACCEPT_LANGUAGE=language).json() if row['id']==location.pk)
        assert row['name']==expected and row['name_fa']=='فابریکه دوم'
    assert AuditEvent.objects.filter(business=business,action='catalog:locations',target=str(location.pk)).exists()


def test_rejects_mixed_fields_and_placeholder_without_financial_effect(environment):
    user,business,*_=environment;client=client_for(user,business)
    before=(Location.objects.count(),Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    for fields in [{'name':'فابریکه / Factory -- کدام'}, {'name_fa':'فابریکه / Factory'}, {'name_fa':'فابریکه','name_en':'Factory / فابریکه'}, {'name_fa':'فابریکه -- کدام'}]:
        result=client.post('/api/catalog/locations/',{'code':'BAD',**fields},content_type='application/json',HTTP_ACCEPT_LANGUAGE='fa')
        assert result.status_code==400,result.content
        assert result.json()['translation_complete'] is True
    assert before==(Location.objects.count(),Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())


def test_warehouse_name_fields_preserve_location_and_business_guards(environment):
    user,business,membership,location,*_=environment;client=client_for(user,business)
    created=client.post('/api/catalog/warehouses/',{'location':location.pk,'name_fa':'گدام جدید','name_en':'New warehouse','kind':'store'},content_type='application/json')
    assert created.status_code==201,created.content
    warehouse=Warehouse.objects.get(pk=created.json()['id'])
    assert warehouse.location_id==location.pk and warehouse.business_id==business.pk
    legacy=client.patch(f'/api/catalog/warehouses/{warehouse.pk}/',{'name':'گدام اصلی'},content_type='application/json')
    assert legacy.status_code==200
    warehouse.refresh_from_db();assert warehouse.name==warehouse.name_fa=='گدام اصلی'
    translated=client.patch(f'/api/catalog/warehouses/{warehouse.pk}/',{'name':'Main warehouse'},content_type='application/json')
    assert translated.status_code==200
    warehouse.refresh_from_db();assert warehouse.name_fa=='گدام اصلی' and warehouse.name_en=='Main warehouse'
    denied=client.get('/api/catalog/warehouses/',HTTP_X_BUSINESS_ID='0')
    assert denied.status_code==403


def test_backfill_splits_only_known_legacy_aliases_and_preserves_unknown_for_review(environment):
    user,business,membership,location,*_=environment
    location.name='فابریکه / Factory -- کدام';location.save(update_fields=['name'])
    warehouse=Warehouse.objects.create(business=business,location=location,name='فابریکه / Factory — گدام')
    unknown=Warehouse.objects.create(business=business,location=location,name='نام مخصوص / Custom trademark')
    before=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    migration=importlib.import_module('erp.migrations.0036_localized_location_warehouse_names')
    migration.split_existing_names(apps,SimpleNamespace(connection=connection))
    location.refresh_from_db();warehouse.refresh_from_db();unknown.refresh_from_db()
    assert location.name==location.name_fa=='فابریکه' and location.name_en=='Factory'
    assert warehouse.name==warehouse.name_fa=='گدام فابریکه' and warehouse.name_en=='Factory warehouse'
    assert unknown.name=='نام مخصوص / Custom trademark'
    assert AuditEvent.objects.filter(action='master_name_review_required',target=f'Warehouse:{unknown.pk}').exists()
    assert before==(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
