import pytest
from django.test import RequestFactory
from rest_framework.exceptions import ErrorDetail
from erp.error_localization import language_for,localize_error_data,translate_message,ERROR_COPY
from erp.tests.test_api import environment,client_for
from erp.models import UserPreference,Entry,StockMovement,Document


def test_exact_copy_preserves_field_structure_codes_and_unsupported_diagnostics():
    original={'error':'The accounting period is closed.','details':{'amount':[ErrorDetail('This field is required.',code='required')],'reference':['Customer wrote: The accounting period is closed.']}}
    value=localize_error_data(original,'ps',400)
    assert value['error']=='د حسابدارۍ دوره تړل شوې ده.'
    assert value['details']['amount'][0].code=='required'
    assert value['details']['reference']==original['details']['reference']
    assert value['error_original']==original
    assert value['translation_complete'] is False and 'اصلي جزیات' in value['error_summary']
    assert original['error']=='The accounting period is closed.'
    assert value['error_code']=='validation_error'


def test_exact_templates_do_not_translate_arbitrary_substrings_or_values():
    assert translate_message('Unconfigured account: CASH','ps')==('حساب نه دی تنظیم شوی: CASH',True)
    assert translate_message('Unconfigured account: customer note','ps')==('Unconfigured account: customer note',False)
    assert translate_message('Customer note Insufficient stock in the selected warehouse/profile.','fa')[1] is False
    assert all(fa and ps for fa,ps in ERROR_COPY.values())


def test_error_language_negotiation_quality_preference_and_primary_dari(environment):
    user,business,*_=environment
    factory=RequestFactory();request=factory.get('/',HTTP_ACCEPT_LANGUAGE='fr, ps-AF;q=0.8, en;q=0.7');request.user=user
    assert language_for(request)=='ps'
    UserPreference.objects.update_or_create(user=user,defaults={'language':'en'})
    request=factory.get('/');request.user=user;assert language_for(request)=='en'
    request=factory.get('/',HTTP_ACCEPT_LANGUAGE='ps;q=0,xx');request.user=user;assert language_for(request)=='en'
    request=factory.get('/',HTTP_ACCEPT_LANGUAGE='fa-AF');request.user=user;assert language_for(request)=='fa'
    request=factory.get('/');assert language_for(request)=='fa'


@pytest.mark.django_db
def test_api_permission_error_is_localized_without_financial_effect(environment):
    user,business,*_=environment
    client=client_for(user,business)
    before=(Entry.objects.count(),StockMovement.objects.count(),Document.objects.count())
    denied=client.get('/api/catalog/',HTTP_X_BUSINESS_ID='0',HTTP_ACCEPT_LANGUAGE='ps-AF')
    assert denied.status_code==403 and denied.json()['error_code']=='permission_denied'
    assert denied['Content-Language']=='ps-AF'
    assert denied.json()['error']=='خپله اجازه لرونکې سوداګري وټاکئ.'
    assert denied.json()['error_original']['error']=='Select an assigned business.'
    english=client.get('/api/catalog/',HTTP_X_BUSINESS_ID='0',HTTP_ACCEPT_LANGUAGE='en')
    assert english.json()['error']=='Select an assigned business.'
    assert english.json()['translation_complete'] is True
    assert (Entry.objects.count(),StockMovement.objects.count(),Document.objects.count())==before
