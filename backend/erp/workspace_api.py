from django.core.exceptions import ValidationError
from .api import Boundary,response
from .daily_workspace import workspace,queue,select_persona
from .guidance import catalog,save_progress


class WorkspaceAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request);location=request.query_params.get('location') or request.headers.get('X-Location-ID')
        if request.query_params.get('queue'):return response(queue(ctx,request.query_params['queue'],location,request.query_params.get('before')))
        return response(workspace(ctx,request.query_params.get('persona'),location))
    def patch(self,request):return response(select_persona(self.ctx(request),request.data.get('persona')))


class GuidanceAPI(Boundary):
    def get(self,request):return response({'topics':catalog(self.ctx(request)),'learning_only':True})
    def patch(self,request):return response(save_progress(self.ctx(request),request.data.get('topic'),request.data.get('completed')))
