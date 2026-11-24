from django.core.exceptions import PermissionDenied,ValidationError
from .api import Boundary,response,doc_permission,document_scope
from .core import get_obj
from .models import ClosingCycle,Membership,PortalListing,CustomerNotice,PortalSubmission,Product
from . import excellence,customer_requests


class ExcellenceAPI(Boundary):
    def get(self,request,section):
        ctx=self.ctx(request)
        if section=='profitability':
            p=dict(request.query_params.items())
            if request.headers.get('X-Location-ID') and not p.get('location'):p['location']=request.headers['X-Location-ID']
            return response(excellence.profitability(ctx,p))
        if section=='closing':
            excellence.full_accountant(ctx)
            ident=request.query_params.get('cycle')
            if ident:return response(excellence.checks(ctx,excellence.cycle_for(ctx,ident)))
            return response({'results':[{'id':c.id,'starts':c.starts,'ends':c.ends,'number':c.source.number,'closed':bool(ctx.business.closed_through and ctx.business.closed_through>=c.ends)} for c in ClosingCycle.objects.filter(business=ctx.business).select_related('source').order_by('-ends')[:100]],
                'current_member':ctx.membership.id,'members':[{'id':m.id,'name':m.user.get_full_name() or m.user.username} for m in excellence.eligible_reviewers(ctx)]})
        if section=='requests':
            ctx.require('sales.view')
            if not ctx.membership.all_locations:raise PermissionDenied('Complete location scope is required for unassigned customer requests.')
            records=[]
            for item in PortalSubmission.objects.filter(business=ctx.business).select_related('grant__party','invoice').order_by('-id'):
                try:customer_requests.staff_submission(ctx,item.id)
                except (PermissionDenied,ValidationError):continue
                records.append(customer_requests.submission_row(item,True))
            return response({'results':records[:100],'truncated':len(records)>100})
        if section=='listings':
            ctx.require('users.manage');ctx.require('sales.view')
            if not ctx.membership.all_locations:raise PermissionDenied('Complete location scope is required.')
            records=[]
            for row in PortalListing.objects.filter(business=ctx.business).select_related('grant__party','product'):
                if ctx.line_allowed(row.product.line):records.append({'id':row.id,'grant':row.grant_id,'customer':row.grant.party.name,'product':row.product_id,'product_name':row.product.name,'profile':row.profile,'active':row.active})
            from .models import PortalGrant
            return response({'results':records,'grants':[{'id':g.id,'name':g.party.name} for g in PortalGrant.objects.filter(business=ctx.business,active=True).select_related('party')]})
        if section=='notices':
            ctx.require('messaging.send');records=[]
            from .customer_notices import notice_for,TEMPLATES
            for item in CustomerNotice.objects.filter(business=ctx.business).select_related('document','party').order_by('-id')[:500]:
                try:notice_for(ctx,item.id)
                except (PermissionDenied,ValidationError):continue
                records.append({'id':item.id,'number':item.document.number,'customer':item.party.name,'channel':item.channel,'recipient':item.recipient,'body':item.body,'language':item.language,'template':item.template,'state':item.state,'attempts':item.attempts,'provider_reference':item.provider_reference,'last_error':item.last_error})
            docs=[]
            for doc in document_scope(ctx).filter(state='posted',kind__in=['sale','sales_order']).order_by('-id')[:300]:
                try:doc_permission(ctx,doc)
                except (PermissionDenied,ValidationError):continue
                docs.append({'id':doc.id,'number':doc.number,'kind':doc.kind,'phone':doc.party.phone if doc.party_id else ''})
            import os
            return response({'results':records[:100],'documents':docs,'provider_configured':bool(os.environ.get('ERP_MESSAGE_PROVIDER_URL') and os.environ.get('ERP_MESSAGE_PROVIDER_TOKEN')),'templates':TEMPLATES,'basis':'Prepared or accepted does not mean delivered. Staff-recorded delivery requires provider evidence; live provider/callback acceptance remains unverified.'})
        raise ValidationError('Unknown business workspace.')


class PortalRequestsAPI(Boundary):
    def get(self,request):
        from .portal import grant_for
        grant,_=grant_for(request)
        listings=PortalListing.objects.filter(business=grant.business,grant=grant,active=True,product__active=True).select_related('product')
        return response({'listings':[{'id':x.id,'name':x.product.name,'unit':x.product.unit,'profile':x.profile} for x in listings],
            'results':[customer_requests.submission_row(item) for item in PortalSubmission.objects.filter(business=grant.business,grant=grant).order_by('-id')[:100]],
            'basis':'Requests await staff review. They do not reserve stock, create debt or post accounting entries.'})
    def post(self,request):
        from .portal import grant_for
        grant,_=grant_for(request)
        item,created=customer_requests.submit_request(request,grant)
        return response(customer_requests.submission_row(item),201 if created else 200)
