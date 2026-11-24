from .api import Boundary,response
from .daily_v6 import attention,timeline,trends
from django.db import transaction
from django.core.exceptions import ValidationError
from types import SimpleNamespace

class AttentionAPI(Boundary):
    def get(self,request):return response(attention(self.ctx(request),request.query_params.get('location') or request.headers.get('X-Location-ID')))

class TimelineAPI(Boundary):
    def get(self,request,pk):return response(timeline(self.ctx(request),pk))

class TrendsAPI(Boundary):
    def get(self,request):return response(trends(self.ctx(request),{**request.query_params.dict(),'location':request.query_params.get('location') or request.headers.get('X-Location-ID')}))

class BulkCatalogAPI(Boundary):
    @transaction.atomic
    def post(self,request):
        from .api import CatalogAPI
        from .models import Business
        ctx=self.ctx(request);ctx.require('settings.manage')
        Business.objects.select_for_update().get(pk=ctx.business.pk)
        identifiers=request.data.get('ids',[])
        if request.data.get('resource')!='products' or request.data.get('action')!='deactivate':raise ValidationError('Only explicit product deactivation is supported by this bulk action.')
        if not isinstance(identifiers,list) or not 1<=len(identifiers)<=100 or len(set(map(str,identifiers)))!=len(identifiers):raise ValidationError('Choose1 to100 distinct records.')
        for identifier in identifiers:
            scoped=SimpleNamespace(user=request.user,headers=request.headers,query_params=request.query_params,data={'active':False})
            CatalogAPI().write(scoped,'products',identifier)
        return response({'changed':len(identifiers),'financial_effect':False})

class DraftFieldsAPI(Boundary):
    def get(self,request,pk):
        from .draft_editing import view
        return response(view(self.ctx(request),pk))
    def patch(self,request,pk):
        from .draft_editing import save
        return response(save(self.ctx(request),pk,request.data.get('data'),request.data.get('version')))
    def post(self,request,pk):
        from .draft_editing import undo
        return response(undo(self.ctx(request),pk,request.data.get('undo_event')))
