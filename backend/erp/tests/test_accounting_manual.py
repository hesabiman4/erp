from django.conf import settings
from erp.tests.test_api import environment,client_for
from erp.core import registry
from erp.seed import CHART
from erp.chart import EXTRA_ACCOUNTS
import pytest

@pytest.mark.parametrize('language,filename,source_name',[
    ('fa-AF','Nawa-Accounting-Manual-Dari.pdf','Nawa_Beginner_Accounting_Manual_Dari.pdf'),
    ('en','Nawa-Accounting-Manual-English.pdf','Nawa_Beginner_Accounting_Manual.pdf'),
    ('ps-AF','Nawa-Accounting-Manual-Pashto.pdf','Nawa_Beginner_Accounting_Manual_Pashto.pdf'),
])
def test_beginner_manual_download_is_authorized_pdf(environment,language,filename,source_name):
    user,business,*_=environment;client=client_for(user,business)
    response=client.get('/api/accounting-guide/',{'language':language})
    assert response.status_code==200 and filename in response['Content-Disposition']
    assert response['Content-Type']=='application/pdf'
    assert response['Content-Language']==language
    assert response['Cache-Control']=='private, no-store'
    data=b''.join(response.streaming_content)
    assert data.startswith(b'%PDF-')
    assert data==(settings.ROOT_DIR/'output/pdf'/source_name).read_bytes()
    from erp.models import Membership
    membership=Membership.objects.get(user=user,business=business);membership.role='sales';membership.permissions=[];membership.save()
    assert client.get('/api/accounting-guide/').status_code==403

def test_manual_default_is_dari_and_invalid_language_cannot_choose_a_path(environment):
    user,business,*_=environment;client=client_for(user,business)
    response=client.get('/api/accounting-guide/')
    assert response.status_code==200 and response['Content-Language']=='fa-AF'
    # Consume the stream like a real download. Manually closing an unconsumed
    # test response sends request_finished inside pytest's database transaction.
    assert b''.join(response.streaming_content).startswith(b'%PDF-')
    assert client.get('/api/accounting-guide/',{'language':'../../.env.local'}).status_code==400

def test_both_manual_sources_cover_all_actions_and_accounts():
    for name in ['CHART_OF_ACCOUNTS_BEGINNER_MANUAL.md','CHART_OF_ACCOUNTS_BEGINNER_MANUAL_DARI.md','CHART_OF_ACCOUNTS_BEGINNER_MANUAL_PASHTO.md']:
        text=(settings.ROOT_DIR/'docs'/name).read_text(encoding='utf-8')
        for action in registry():assert f'`{action}`' in text,(name,action)
        for code in set(CHART)|set(EXTRA_ACCOUNTS):assert f'`{code}`' in text,(name,code)
