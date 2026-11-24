"""Customer-only read access without staff membership or inventory/cost exposure."""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from .api import Boundary,response
from .core import get_obj,outstanding
from .models import PortalGrant,Document,Allocation,AuditEvent,Party,Product

class PortalAccessAPI(Boundary):
    def authorized(self,request):
        ctx=self.ctx(request);ctx.require('users.manage');ctx.require('sales.view')
        if not ctx.membership.all_locations:raise PermissionDenied('Full business location scope is required to manage customer portal access.')
        if not ctx.has('documents.all_lines') and Product.objects.filter(business=ctx.business).exclude(line__in=ctx.membership.product_lines).exists():raise PermissionDenied('Full business product-line scope is required to manage customer portal access.')
        return ctx
    def get(self,request):
        ctx=self.authorized(request)
        return response({'results':[{'id':g.id,'username':g.user.username,'party':g.party_id,'customer':g.party.name,'active':g.active} for g in PortalGrant.objects.filter(business=ctx.business).select_related('user','party')]})
    @transaction.atomic
    def post(self,request):
        ctx=self.authorized(request);party=get_obj(ctx,Party,request.data['party'])
        if party.kind!='customer':raise ValidationError('Select a customer.')
        username=str(request.data.get('username','')).strip();password=str(request.data.get('password',''));User=get_user_model();candidate=User(username=username)
        if not username or len(username)>150 or User.objects.filter(username=username).exists():raise ValidationError('Choose a new, available portal username.')
        candidate.full_clean(exclude=['password']);validate_password(password,candidate)
        user=User.objects.create_user(username=username,password=password);grant=PortalGrant.objects.create(business=ctx.business,user=user,party=party)
        AuditEvent.objects.create(business=ctx.business,user=request.user,action='portal.grant',target=str(grant.id),details={'user':user.id,'party':party.id})
        return response({'id':grant.id,'username':user.username,'active':True,'staff_membership':False},201)
    @transaction.atomic
    def patch(self,request):
        ctx=self.authorized(request);grant=get_obj(ctx,PortalGrant,request.data['id']);active=request.data.get('active')
        if not isinstance(active,bool):raise ValidationError('active must be true or false.')
        grant.active=active;grant.save(update_fields=['active']);AuditEvent.objects.create(business=ctx.business,user=request.user,action='portal.access',target=str(grant.id),details={'active':active})
        return response({'id':grant.id,'active':active})

def grant_for(request):
    grants=PortalGrant.objects.filter(user=request.user,active=True,party__kind='customer').select_related('business','party');value=request.query_params.get('grant')
    grant=grants.filter(pk=value).first() if value else grants.first()
    if not grant:raise PermissionDenied('No active customer portal grant.')
    return grant,grants

def invoice_row(doc):
    row={'id':doc.id,'number':doc.number,'date':doc.date,'total':doc.amount,'outstanding':outstanding(doc),'location':doc.location.name if doc.location_id else '',
       'lines':[{key:line[key] for key in ['product_name','quantity','unit_price','amount','thickness_mm','sheet_count','length_mm','width_mm'] if key in line} for line in doc.result.get('lines',[])],
       'payments':[{'number':a.document.number,'date':a.document.date,'historical_allocation_afn':a.amount,'foreign_amount':a.document.result.get('foreign_amount'),'foreign_currency':a.document.result.get('currency')} for a in Allocation.objects.filter(invoice=doc,document__state='posted').select_related('document')]}
    from .models import ForeignExposure,DeliveryConfirmation
    exposure=ForeignExposure.objects.filter(invoice=doc).first()
    if exposure:
        from .foreign import exposure_balance
        qty,value=exposure_balance(exposure);row['foreign']={'currency':exposure.currency,'amount':exposure.foreign_amount,'remaining':qty,'carrying_afn':value}
    row['delivery_confirmed']=DeliveryConfirmation.objects.filter(invoice=doc).exists()
    return row

class PortalAPI(Boundary):
    def get(self,request,pk=None):
        grant,grants=grant_for(request);query=Document.objects.filter(business=grant.business,party=grant.party,state='posted',kind__in=['sale','opening_receivable'])
        if pk:
            doc=query.filter(pk=pk).first()
            if not doc:raise PermissionDenied('This invoice is outside your customer account.')
            return response(invoice_row(doc))
        try:offset=max(0,int(request.query_params.get('offset',0)))
        except ValueError:raise ValidationError('Use integer pagination.')
        return response({'grants':[{'id':g.id,'business':g.business.name,'customer':g.party.name} for g in grants], 'grant':grant.id,'business':grant.business.name,'customer':grant.party.name,'currency':grant.business.currency,
          'results':[invoice_row(doc) for doc in query.order_by('-date','-id')[offset:offset+50]],'count':query.count(),'next_offset':offset+50 if offset+50<query.count() else None,'read_only':True})

class PortalPrintAPI(Boundary):
    def get(self,request,pk):
        grant,_=grant_for(request);doc=Document.objects.filter(pk=pk,business=grant.business,party=grant.party,state='posted',kind__in=['sale','opening_receivable']).first()
        if not doc:raise PermissionDenied('This invoice is outside your customer account.')
        row=invoice_row(doc)
        from .localization import printed_date
        from .document_print import context as print_context,number
        # Keep the portal projection explicit: never pass the unrestricted
        # result (carrying costs, input consumption or internal fields).
        snapshot=doc.result.get('customer_snapshot') or {'name':grant.party.name,'phone':grant.party.phone,'address':grant.party.address}
        view=print_context(grant.business,doc,{'amount':row['total'],'balance':row['outstanding'],'result':{'lines':row['lines'],'customer_snapshot':snapshot}},request.user)
        view['allocations_label']='رویدادهای تسویه این بل / Invoice settlement history'
        view['allocation_reference_label']='شماره سند / Document number'
        view['allocations']=[{'number':payment['number'],'date':printed_date(payment['date'],request.user),'amount_display':number(payment['historical_allocation_afn'],True)} for payment in row['payments']]
        from .print_settings import profile_for
        from .print_profiles import effective
        from .print_copy import apply
        apply(view,effective(profile_for(grant.business),doc.kind,request.query_params))
        html=render_to_string('document.html',view)
        AuditEvent.objects.create(business=grant.business,user=request.user,action='portal.print',target=str(doc.id))
        return HttpResponse(html,content_type='text/html; charset=utf-8')
