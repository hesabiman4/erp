"""Session-authenticated, business-scoped HTTP boundary."""
import csv
import hashlib
import io
import json
import mimetypes
from urllib.parse import unquote
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from django.contrib.auth import authenticate, login, logout, password_validation
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import IntegrityError, transaction, models
from django.db.models import Q, Sum
from django.http import FileResponse, HttpResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import serializers
from .models import *
from .core import Context, execute, get_obj, outstanding, json_value, registry

def response(data,status=200): return Response(json_value(data),status=status)

class Boundary(APIView):
    def finalize_response(self,request,response,*args,**kwargs):
        response=super().finalize_response(request,response,*args,**kwargs)
        response['Cache-Control']='private, no-store'
        if response.status_code>=400 and hasattr(response,'data'):
            from .error_localization import language_for,localize_error_data
            language=language_for(request)
            response.data=localize_error_data(response.data,language,response.status_code)
            response['Content-Language']={'fa':'fa-AF','ps':'ps-AF','en':'en'}[language]
        return response
    def handle_exception(self,exc):
        if isinstance(exc,ValidationError):
            return response({'error':'; '.join(exc.messages),'details':getattr(exc,'message_dict',{})},400)
        if isinstance(exc,PermissionDenied): return response({'error':str(exc)},403)
        if isinstance(exc,IntegrityError): return response({'error':'This operation conflicts with an existing or protected record.'},409)
        if isinstance(exc,(KeyError,ValueError,InvalidOperation)):
            return response({'error':'Invalid or missing field: '+str(exc)},400)
        return super().handle_exception(exc)
    def ctx(self,request):
        try: business=Business.objects.get(pk=int(request.headers.get('X-Business-ID') or request.query_params.get('business','0')))
        except (ValueError,Business.DoesNotExist): raise PermissionDenied('Select an assigned business.')
        ctx=Context(request.user,business)
        ctx.cash_reason=unquote(str(request.headers.get('X-Cash-Reason','')),encoding='utf-8',errors='strict')
        return ctx

def user_data(user):
    from .models import PortalGrant
    return {'id':user.pk,'username':user.username,'name':user.get_full_name() or user.username,'portal_only':not Membership.objects.filter(user=user,active=True).exists() and PortalGrant.objects.filter(user=user,active=True).exists()}

@method_decorator(ensure_csrf_cookie,name='dispatch')
@method_decorator(csrf_protect,name='dispatch')
class SessionAPI(Boundary):
    permission_classes=[AllowAny]
    def get(self,request):
        return response({'user':user_data(request.user) if request.user.is_authenticated else None,'csrfToken':get_token(request),'mfa_enabled':TOTPDevice.objects.filter(user=request.user,confirmed=True).exists() if request.user.is_authenticated else False})
    def post(self,request):
        username=str(request.data.get('username','')).strip()
        key=hashlib.sha256((request.META.get('REMOTE_ADDR','')+':'+username.lower()).encode()).hexdigest()
        attempt,_=LoginAttempt.objects.get_or_create(key=key,defaults={'last_at':timezone.now()})
        if attempt.failures>=5 and attempt.last_at>timezone.now()-timedelta(minutes=15): return response({'error':'Too many login attempts. Try again after 15 minutes.'},429)
        user=authenticate(request,username=username,password=request.data.get('password',''))
        device=None
        if user:
            devices=TOTPDevice.objects.filter(user=user,confirmed=True)
            if devices.exists():
                device=next((d for d in devices if d.verify_token(request.data.get('otp',''))),None)
                if not device: user=None
        if not user:
            attempt.failures=attempt.failures+1 if attempt.last_at>timezone.now()-timedelta(minutes=15) else 1
            attempt.last_at=timezone.now(); attempt.save()
            return response({'error':'Invalid credentials or verification code.'},400)
        attempt.failures=0; attempt.save(update_fields=['failures'])
        login(request,user)
        if device: otp_login(request,device)
        return response({'user':user_data(user),'csrfToken':get_token(request)})

class LogoutAPI(Boundary):
    def post(self,request):
        logout(request); return response({'ok':True})

class ContextAPI(Boundary):
    def get(self,request):
        memberships=Membership.objects.filter(user=request.user,active=True).select_related('business').order_by('business_id')
        return response({'user':user_data(request.user),'businesses':[{'id':m.business_id,'name':m.business.name,'slug':m.business.slug,'manufacturing_mode':m.business.manufacturing_mode,'currency':m.business.currency,'membership':{'role':m.role,'permissions':m.permissions,'all_locations':m.all_locations,'location_ids':m.location_ids,'product_lines':m.product_lines,'approval_limit':m.approval_limit}} for m in memberships]})

RESOURCES={'locations':Location,'warehouses':Warehouse,'products':Product,'parties':Party,'employees':Employee,'departments':Department,'positions':Position,'accounts':Account,'boms':BOM,'assets':Asset,'tax_rules':TaxRule,'memberships':Membership}
PRIVATE_FIELDS={'id','business','created_by','created_at','posted_at'}

def serialize_model(obj,language=None):
    data={}
    for field in obj._meta.fields:
        if field.name in ('business','request_hash','idempotency_key'): continue
        value=getattr(obj,field.attname)
        data[field.name]=json_value(value)
    if language and isinstance(obj,(Location,Warehouse)):
        from .master_names import language_name
        data['name']=language_name(obj,language)
    return data

def scope_queryset(ctx,Model):
    qs=Model.objects.filter(business=ctx.business)
    if Model is Location and not ctx.membership.all_locations: qs=qs.filter(id__in=ctx.membership.location_ids)
    if Model in (Warehouse,Employee,Asset) and not ctx.membership.all_locations: qs=qs.filter(location_id__in=ctx.membership.location_ids)
    if Model is Department and not ctx.membership.all_locations: qs=qs.filter(Q(location__isnull=True)|Q(location_id__in=ctx.membership.location_ids))
    if Model is Position and not ctx.membership.all_locations: qs=qs.filter(Q(department__location__isnull=True)|Q(department__location_id__in=ctx.membership.location_ids))
    if Model is Product: qs=qs.filter(line__in=ctx.membership.product_lines)
    if Model is BOM: qs=qs.filter(product__line__in=ctx.membership.product_lines)
    return qs.order_by('pk')

def can(ctx,*permissions): return any(ctx.has(p) for p in permissions)

class CatalogAPI(Boundary):
    def get(self,request,resource=None,pk=None):
        ctx=self.ctx(request)
        from .error_localization import language_for
        language=language_for(request)
        if resource is not None and resource not in RESOURCES: raise ValidationError('Unknown catalog resource.')
        result={'business':{'id':ctx.business.pk,'name':ctx.business.name,'manufacturing_mode':ctx.business.manufacturing_mode,'currency':ctx.business.currency,'closed_through':ctx.business.closed_through,'settings':ctx.business.settings}}
        for name,Model in RESOURCES.items():
            permitted=True
            if name in ('employees','departments','positions'): permitted=can(ctx,'payroll.view','payroll.post','payroll.manage')
            if name=='boms': permitted=can(ctx,'bom.view','consumption.view') and ctx.business.manufacturing_mode=='bom'
            if name in ('assets','accounts'): permitted=can(ctx,'finance.view','accounting.view','accounting.post','finance.post')
            if name=='memberships': permitted=ctx.has('users.manage')
            query=scope_queryset(ctx,Model)
            if Model is Product and not can(ctx,'inventory.raw','consumption.view'): query=query.exclude(kind='raw')
            if Model is Party:
                kinds=[]
                if can(ctx,'sales.view','sales.post','sales.collect','settings.manage'): kinds.append('customer')
                if can(ctx,'purchases.view','purchases.post','purchases.pay','finance.view','finance.post','settings.manage'): kinds.append('supplier')
                query=query.filter(kind__in=kinds)
            result[name]=[redact(ctx,serialize_model(x,language)) for x in query[:1000]] if permitted else []
            if Model is Party and not can(ctx,'settings.manage','sales.credit_manage','sales.credit_summary'):
                for party in result[name]:
                    for field in ('credit_limit','credit_hold','block_overdue'):party.pop(field,None)
        return response(result if resource is None else result.get(resource,[]))
    def post(self,request,resource,pk=None): return self.write(request,resource,pk)
    def patch(self,request,resource,pk): return self.write(request,resource,pk)
    @transaction.atomic
    def write(self,request,resource,pk):
        ctx=self.ctx(request)
        if resource not in RESOURCES: raise ValidationError('Unknown catalog resource.')
        Model=RESOURCES[resource]
        if resource=='assets': raise ValidationError('Use the asset acquisition/depreciation workflows to preserve accounting history.')
        if resource=='memberships': ctx.require('users.manage')
        elif resource in ('accounts','tax_rules'):
            ctx.require('accounting.manage')
        elif resource=='parties':
            if not can(ctx,'settings.manage','sales.post','purchases.post'): raise PermissionDenied('Customer/supplier editing is restricted.')
        elif resource in ('employees','departments','positions'):
            if not can(ctx,'settings.manage','payroll.manage'): raise PermissionDenied('Employee terms are restricted.')
        else: ctx.require('settings.manage')
        # Serialize employment/rate changes with payroll posting's business lock.
        if resource in ('employees','departments','positions','parties'):
            Business.objects.select_for_update().get(pk=ctx.business.pk)
            ctx=Context(request.user,ctx.business)
        if resource=='memberships':
            Business.objects.select_for_update().get(pk=ctx.business.pk)
            ctx=Context(request.user,ctx.business);ctx.require('users.manage')
        obj=get_obj(ctx,Model,pk) if pk else Model(business=ctx.business)
        previous=serialize_model(obj) if pk else {}
        if resource=='boms' and pk and obj.approved: raise ValidationError('An approved BOM version is immutable. Create a new version.')
        data=dict(request.data)
        if Model in (Location,Warehouse):
            from .master_names import prepare_name_payload
            prepare_name_payload(obj,data)
        if resource=='parties':
            from .party_profiles import authorize
            if pk:authorize(ctx,obj.kind,edit=True)
            target_kind=data.get('kind',obj.kind);authorize(ctx,target_kind,edit=True)
            if pk and target_kind!=obj.kind and Document.objects.filter(business=ctx.business,party=obj).exists():
                raise ValidationError('A used customer/supplier type cannot be changed.')
        if resource=='memberships':
            if 'access_role' in data: raise ValidationError('Use the role assignment editor to assign a saved role.')
            if any(k in data for k in ('permissions','role')):obj.access_role=None
        if resource=='employees' and pk:
            history=Document.objects.filter(business=ctx.business,employee=obj,state='posted',kind='payroll_accrue')
            if history.exists():
                if any(key in data and str(data[key])!=str(getattr(obj,'location_id' if key=='location' else key)) for key in ('kind','week_start','location','join_date')):
                    raise ValidationError('Accrued employment basis/location/start date is preserved. Use a reviewed new contract instead of rewriting payroll history.')
                if 'terms' in data and data['terms'].get('rate_basis','day')!=obj.terms.get('rate_basis','day'):
                    raise ValidationError('The rate basis used by posted payroll cannot be changed.')
                if data.get('end_date') and any(str(data['end_date'])<pay.data.get('earning_through',pay.date.isoformat()) for pay in history):
                    raise ValidationError('Employment cannot end before already accrued earnings.')
        if pk and resource=='departments' and 'location' in data and data['location']!=obj.location_id and Employee.objects.filter(department=obj).exists():
            raise ValidationError('Reassign staff before changing their department location.')
        if pk and resource=='positions' and 'department' in data and data['department']!=obj.department_id and Employee.objects.filter(position=obj).exists():
            raise ValidationError('Reassign staff before changing their position department.')
        if resource=='parties' and any(k in data for k in ('credit_limit','credit_hold','block_overdue','payment_terms_days')):
            supplier=data.get('kind',obj.kind)=='supplier'
            manager='purchases.terms_manage' if supplier else 'sales.credit_manage'
            if not can(ctx,'settings.manage',manager):raise PermissionDenied('Supplier payment terms require authorized terms management.' if supplier else 'Credit terms require authorized credit management.')
            if supplier and any(k in data for k in ('credit_limit','credit_hold','block_overdue')):
                raise ValidationError('Customer credit controls are not supplier payment terms.')
            from .core import D
            if data.get('credit_limit') is not None and 'credit_limit' in data:data['credit_limit']=D(data['credit_limit'])
            if 'payment_terms_days' in data and (isinstance(data['payment_terms_days'],bool) or not str(data['payment_terms_days']).isdigit()):raise ValidationError('Payment terms must be between 0 and 365 days.')
            if any(k in data and not isinstance(data[k],bool) for k in ('credit_hold','block_overdue')):raise ValidationError('Select a valid credit hold option.')
        if resource=='parties' and not ctx.has('settings.manage'):
            kind=data.get('kind',obj.kind)
            if kind=='customer' and not can(ctx,'sales.post','sales.collect'): raise PermissionDenied('Customer editing requires sales permission.')
            if kind=='supplier' and not can(ctx,'purchases.post','finance.post'): raise PermissionDenied('Supplier editing requires purchasing or finance permission.')
        if resource=='products' and pk and StockPool.objects.filter(product=obj).exists():
            if any(key in data and str(data[key])!=str(getattr(obj,key)) for key in ('unit','line','kind')):
                raise ValidationError('Stocked product unit, product line, and kind cannot be changed. Create a new product and use an approved reclassification.')
        if resource=='accounts' and pk and Entry.objects.filter(account=obj).exists():
            if any(key in data and data[key]!=getattr(obj,key) for key in ('code','category','control')):
                raise ValidationError('A used account code, category, or control status is immutable. Create a new account for future use.')
        rate_effective=data.pop('effective_date',None) if resource=='employees' else None
        if resource=='employees' and 'terms' in data:
            existing_rates=obj.terms.get('rates',[]) if obj.pk else []
            if data['terms'].get('rates',[])!=existing_rates: raise ValidationError('Use an effective-dated rate change instead of replacing historical rates.')
        if resource=='memberships' and not pk and data.get('username'):
            username=data.pop('username'); password=data.pop('password','')
            password_validation.validate_password(password)
            user=User.objects.create_user(username=username,password=password)
            data['user']=user.pk
        allowed={f.name:f for f in Model._meta.fields if f.name not in PRIVATE_FIELDS}
        for key,value in data.items():
            if key not in allowed: raise ValidationError('Unknown/read-only field: '+key)
            f=allowed[key]
            if isinstance(f,models.ForeignKey):
                related=f.remote_field.model
                if related is User:
                    if not User.objects.filter(pk=value).exists(): raise ValidationError('Invalid user.')
                    setattr(obj,f.attname,value)
                elif value is None and f.null: setattr(obj,key,None)
                else: setattr(obj,key,get_obj(ctx,related,value))
            else: setattr(obj,key,value)
        if resource=='employees' and 'rate' in data:
            from .finance import update_employee_rate
            from .core import D
            if not obj.pk or Employee.objects.get(pk=obj.pk).rate!=D(data['rate']):
                update_employee_rate(obj,data['rate'],rate_effective)
        if resource=='memberships':
            from .access_control import protect_membership
            protect_membership(ctx,obj,Membership.objects.get(pk=pk) if pk else None)
        obj.full_clean(); obj.save()
        if resource=='memberships':
            for location_id in obj.location_ids: get_obj(ctx,Location,location_id)
            if not ctx.has('users.grant_all') and '*' not in ctx.membership.permissions:
                if any(not ctx.has(grant) for grant in obj.permissions) or (obj.all_locations and not ctx.membership.all_locations):
                    raise PermissionDenied('You cannot grant privileges outside your own assignment.')
                if not set(obj.product_lines).issubset(set(ctx.membership.product_lines)) or obj.approval_limit>ctx.membership.approval_limit:
                    raise PermissionDenied('You cannot grant product lines or approval limits beyond your own assignment.')
        if resource=='boms':
            if any(row.get('bom') for row in obj.components):
                from .jobs import validate_nested_bom
                validate_nested_bom(ctx,obj)
            for item in obj.components:
                get_obj(ctx,Product,item['product'])
                from .core import D
                if D(item['quantity'])<=0: raise ValidationError('BOM component quantity must be positive.')
        current=serialize_model(obj)
        changes={key:{'before':previous.get(key),'after':current.get(key)} for key in data if previous.get(key)!=current.get(key)}
        AuditEvent.objects.create(business=ctx.business,user=request.user,action='catalog:'+resource,target=str(obj.pk),details={'resource':resource,'fields':list(data),'changes':changes})
        return response(serialize_model(obj),201 if not pk else 200)

def document_scope(ctx):
    qs=Document.objects.filter(business=ctx.business).select_related('party','location','warehouse','employee')
    if not ctx.membership.all_locations:
        destinations=Warehouse.objects.filter(business=ctx.business,location_id__in=ctx.membership.location_ids).values_list('id',flat=True)
        incoming=Q()
        for warehouse_id in destinations: incoming|=Q(kind='transfer_dispatch',result__destination=warehouse_id)
        qs=qs.filter(Q(location_id__in=ctx.membership.location_ids)|incoming)
    return qs

def doc_permission(ctx,doc):
    if doc.kind=='money_instrument':
        from .money_instruments import whole_pool
        whole_pool(ctx)
    from .capture import document_guard as capture_document_guard
    capture_document_guard(ctx,doc)
    from .crm import document_guard as crm_document_guard
    crm_document_guard(ctx,doc)
    from .statement_imports import document_guard as statement_guard
    from .sourcing import document_guard as sourcing_guard
    statement_guard(ctx,doc);sourcing_guard(ctx,doc)
    from .cashier_shifts import document_guard as cash_document_guard
    cash_document_guard(ctx,doc)
    from .procurement import document_guard
    document_guard(ctx,doc)
    if doc.kind.startswith('closing_'):
        from .excellence import full_accountant
        full_accountant(ctx)
    if doc.kind=='portal_review':
        from .customer_requests import staff_submission
        staff_submission(ctx,doc.result.get('submission') or doc.data.get('submission'))
    if doc.kind=='portal_listing':ctx.require('users.manage')
    if doc.kind.startswith('notice_'):
        from .customer_notices import notice_document,notice_for
        if doc.kind=='notice_prepare':notice_document(ctx,doc.result.get('document') or doc.data.get('document'))
        else:notice_for(ctx,doc.result.get('notice') or doc.data.get('notice'))
    get_obj(ctx,Document,doc.pk)
    if doc.kind.startswith('late_cost_'):ctx.require('cost.view')
    if doc.kind=='job_bom_plan':
        ctx.require('bom.view');ctx.require('consumption.view')
    if doc.kind in {'cut_plan','cut_execute'} and doc.result.get('plan'):
        from .order_cutting import authorize_plan
        plan=get_obj(ctx,CutPlan,doc.result['plan']);authorize_plan(ctx,plan)
    action=registry().get(doc.kind)
    prefix=action[0].split('.')[0] if action else 'documents'
    if not can(ctx,prefix+'.view',prefix+'.post','documents.view',action[0] if action else 'documents.view'): raise PermissionDenied('Document access is restricted.')
    if prefix=='payroll' and not can(ctx,'payroll.view','payroll.post'): raise PermissionDenied('Payroll access is restricted.')
    if doc.employee_id and not can(ctx,'payroll.view','payroll.post'): raise PermissionDenied('Employee financial documents are restricted.')
    if doc.kind in ('material_issue','material_return','production_material_return','production_consume') and not can(ctx,'inventory.raw','consumption.view'):
        raise PermissionDenied('Raw-material movement details are restricted.')
    if doc.kind in ('stock_opening','stock_adjust','purchase_order','purchase_receive','purchase_bill','purchase_return') and not can(ctx,'inventory.raw','consumption.view'):
        product_ids=[item.get('product') for item in doc.result.get('lines',[]) if isinstance(item,dict)]
        if Product.objects.filter(business=ctx.business,pk__in=product_ids,kind='raw').exists(): raise PermissionDenied('Raw-material transaction details are restricted.')

def redact(ctx,value):
    forbidden=set()
    if not ctx.has('cost.view'): forbidden.update(['cost','costs','value','average_cost','unit_cost','cost_per_cm','total_cost','input_cost','material_cost','output_value','carrying_value','residual','accounting','labor_cost','overhead_cost','abnormal_loss','byproduct_value','main_value','wip_in','wip_out','wip_remaining','allocated_cost','output_cost','allowance_released','allowance_restored','conversion_allocations'])
    if not ctx.has('consumption.view'): forbidden.update(['inputs','consumption','components','expected_inputs','actual_inputs','conversion_sources','conversion_allocations'])
    if not can(ctx,'consumption.view','bom.view'): forbidden.update(['bom','expected'])
    if isinstance(value,dict): return {k:redact(ctx,v) for k,v in value.items() if k not in forbidden and (ctx.has('cost.view') or not k.endswith('_cost'))}
    if isinstance(value,list): return [redact(ctx,v) for v in value]
    return value

def public_result(ctx,doc,value):
    from .procurement import public_result as procurement_public_result
    result=redact(ctx,procurement_public_result(ctx,doc,value))
    stock_cost_kinds={'stock_opening','stock_adjust','stock_count_adjust','production','production_start','production_consume','production_complete','production_bom','trim','cut','material_issue','material_return','transfer_dispatch','transfer_receive','transfer_resolve','production_material_return','inventory_write_down','inventory_write_down_reverse'}
    hide_cost=not ctx.has('cost.view') and doc.kind in stock_cost_kinds
    hide_charge=not can(ctx,'transfers.settle','finance.view')
    def prune(item):
        if isinstance(item,dict):
            return {key:prune(val) for key,val in item.items() if not (hide_cost and key in {'total','amount','total_value','cost_value','loss_value','main_cost','trim_values'}) and not (hide_charge and key in {'internal_charge','remaining_internal_charge','internal_outstanding','charge_delta'})}
        if isinstance(item,list): return [prune(val) for val in item]
        return item
    return prune(result)

def document_data(ctx,doc,include_flow=True):
    doc_permission(ctx,doc)
    result=serialize_model(doc)
    result['balance']=outstanding(doc) if doc.kind in ('sale','purchase_bill','opening_receivable','opening_payable') or (doc.kind in ('expense_post','asset_acquire') and doc.party_id) else None
    result['party_name']=doc.party.name if doc.party else ''
    from .models import ForeignExposure
    exposure=ForeignExposure.objects.filter(invoice=doc).first()
    if exposure:
        from .foreign import exposure_balance
        qty,value=exposure_balance(exposure)
        result['foreign_terms']={'exposure':exposure.id,'currency':exposure.currency,'original_amount':str(exposure.foreign_amount),'rate':str(exposure.initial_rate),'foreign_remaining':str(qty),'carrying_amount':str(value)}
    result['employee_name']=doc.employee.name if doc.employee else ''
    from .sales_flow import commercial_flow
    flow=commercial_flow(ctx,doc) if include_flow or doc.kind in {'quotation','sales_order'} else None
    if flow is not None: result['sales_flow']=flow
    if include_flow:
        linked_ids=set()
        if doc.reference_id:linked_ids.add(doc.reference_id)
        linked_ids.update(Document.objects.filter(business=ctx.business,reference=doc).values_list('pk',flat=True)[:61])
        for allocation in Allocation.objects.filter(Q(invoice=doc)|Q(document=doc)).order_by('pk')[:61]:
            linked_ids.add(allocation.document_id if allocation.invoice_id==doc.pk else allocation.invoice_id)
        linked_ids.discard(doc.pk)
        related=[]
        for linked in Document.objects.filter(business=ctx.business,pk__in=linked_ids).select_related('location','warehouse','employee').order_by('-id')[:60]:
            try:doc_permission(ctx,linked)
            except (PermissionDenied,ValidationError):continue
            related.append({'id':linked.pk,'number':linked.number,'kind':linked.kind,'date':linked.date})
        result['related_documents']=related
    result['attachments']=[{'id':item.pk,'filename':item.filename} for item in Attachment.objects.filter(document=doc,business=ctx.business).order_by('id')]
    result=public_result(ctx,doc,result)
    from .document_register import public_amount
    result['amount']=public_amount(ctx,doc)
    return result

class DocumentsAPI(Boundary):
    def get(self,request,pk=None):
        ctx=self.ctx(request)
        if pk: return response(document_data(ctx,get_obj(ctx,Document,pk)))
        qs=document_scope(ctx).order_by('-id')
        if request.query_params.get('kind'): qs=qs.filter(kind=request.query_params['kind'])
        if request.query_params.get('state'):
            state=request.query_params['state']
            if state not in {'draft','posted','requested','approved','rejected','converted','cancelled'}:raise ValidationError('Select a valid document state.')
            qs=qs.filter(state=state)
        if request.query_params.get('q'):
            query=request.query_params['q']; qs=qs.filter(Q(number__icontains=query)|Q(party__name__icontains=query)|Q(party__phone__icontains=query))
        location=request.query_params.get('location') or request.headers.get('X-Location-ID')
        if location:
            loc=get_obj(ctx,Location,location)
            qs=qs.filter(location=loc)
        if not ctx.has('documents.all_lines'): qs=qs.filter(product_lines__contained_by=ctx.membership.product_lines)
        if not can(ctx,'payroll.view','payroll.post'): qs=qs.filter(employee__isnull=True)
        visible_kinds=[]
        for kind,(permission,_) in registry().items():
            prefix=permission.split('.')[0]
            if can(ctx,permission,prefix+'.view',prefix+'.post','documents.view'): visible_kinds.append(kind)
        qs=qs.filter(kind__in=visible_kinds)
        try: limit=max(1,min(200,int(request.query_params.get('limit',100))));offset=max(0,int(request.query_params.get('offset',0)))
        except ValueError: raise ValidationError('Pagination requires integer limit/offset.')
        count=qs.count()
        rows=[]
        for doc in qs[offset:offset+limit]:
            try: rows.append(document_data(ctx,doc,include_flow=False))
            except PermissionDenied: continue
        return response({'results':rows,'count':count,'next_offset':offset+limit if offset+limit<count else None,'offset':offset,'limit':limit})
    @transaction.atomic
    def post(self,request,pk=None):
        from .core import create_draft
        ctx=self.ctx(request)
        doc=create_draft(ctx,request.data.get('kind'),request.data.get('data',{}),request.headers.get('Idempotency-Key'))
        return response(document_data(ctx,doc),200 if getattr(doc,'_draft_replayed',False) else 201)
    @transaction.atomic
    def patch(self,request,pk):
        ctx=self.ctx(request); Business.objects.select_for_update().get(pk=ctx.business.pk)
        doc=get_obj(ctx,Document,pk); doc_permission(ctx,doc)
        ctx.require('drafts.create')
        if doc.state!='draft': raise ValidationError('Posted documents cannot be edited.')
        from .capture_models import CaptureReview
        if CaptureReview.objects.filter(draft=doc).exists():raise ValidationError('Captured draft fields were approved against the original. They cannot be silently edited after review; use the preserved review and ordinary correction workflow.')
        from .draft_editing import save,token
        save(ctx,doc.pk,request.data.get('data',doc.data),request.data.get('version') or token(doc))
        doc.refresh_from_db()
        return response(document_data(ctx,doc))

class OperationAPI(Boundary):
    def post(self,request,action):
        ctx=self.ctx(request)
        payload=dict(request.data)
        if request.headers.get('X-Cash-Reason'):payload['cash_reason']=ctx.cash_reason
        doc=execute(ctx,action,payload,request.headers.get('Idempotency-Key'))
        return response({'document':document_data(ctx,doc),'result':public_result(ctx,doc,doc.result)},201)

class StockAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request)
        if not can(ctx,'inventory.view','sales.post','production.post','transfers.post','purchases.post'): raise PermissionDenied('Inventory access is restricted.')
        wh=scope_queryset(ctx,Warehouse)
        pools=StockPool.objects.filter(business=ctx.business,warehouse__in=wh,product__line__in=ctx.membership.product_lines).select_related('product','warehouse')
        if not can(ctx,'inventory.raw','consumption.view'): pools=pools.exclude(product__kind='raw')
        blocks=Block.objects.filter(business=ctx.business,warehouse__in=wh,product__line__in=ctx.membership.product_lines)
        if request.query_params.get('warehouse'):
            pools=pools.filter(warehouse_id=request.query_params['warehouse']); blocks=blocks.filter(warehouse_id=request.query_params['warehouse'])
        location=request.query_params.get('location') or request.headers.get('X-Location-ID')
        if location:
            loc=get_obj(ctx,Location,location); pools=pools.filter(warehouse__location=loc); blocks=blocks.filter(warehouse__location=loc)
        rows=[]
        for pool in pools.order_by('id')[:2000]:
            item=serialize_model(pool); item['product_name']=pool.product.name; item['warehouse_name']=pool.warehouse.name; item['unit']=pool.product.unit
            item['average_cost']=pool.value/pool.quantity if pool.quantity else Decimal('0')
            item['available_quantity']=pool.quantity if pool.warehouse.kind!='transit' else Decimal('0')
            if pool.product.unit=='cm':
                pieces=Block.objects.filter(business=ctx.business,product=pool.product,warehouse=pool.warehouse,profile=pool.profile,status__in=['ready','reserved'])
                item['available_quantity']=sum((b.remaining_height_mm-b.reserved_height_mm for b in pieces),Decimal('0'))/10
            rows.append(redact(ctx,item))
        return response({'pools':rows,'blocks':[serialize_model(x) for x in blocks.order_by('-id')[:2000]]})

class ReportsAPI(Boundary):
    def get(self,request,name):
        from .reports import report
        ctx=self.ctx(request)
        params=dict(request.query_params.items())
        if name not in ('trial_balance','balance_sheet','changes_equity') and request.headers.get('X-Location-ID') and not params.get('location'): params['location']=request.headers['X-Location-ID']
        result=report(ctx,name,params)
        return response(result)

class BankEntriesAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request)
        if not can(ctx,'finance.view','finance.post'): raise PermissionDenied('Bank reconciliation is restricted.')
        query=Entry.objects.filter(document__business=ctx.business,document__state='posted',account__code='BANK').select_related('document','location')
        if not ctx.has('documents.all_lines'): query=query.filter(document__product_lines__contained_by=ctx.membership.product_lines)
        if not ctx.has('payroll.view'): query=query.filter(employee__isnull=True,document__employee__isnull=True)
        if not ctx.membership.all_locations: query=query.filter(location_id__in=ctx.membership.location_ids)
        location=request.query_params.get('location') or request.headers.get('X-Location-ID')
        if location: query=query.filter(location=get_obj(ctx,Location,location))
        instrument=request.query_params.get('bank_instrument')
        if instrument:
            from .money_instruments import instrument_for,entries_for
            selected=instrument_for(ctx,instrument,'BANK',location)
            query=query.filter(pk__in=entries_for(selected).values('pk'))
        through=request.query_params.get('through_date')
        if through:
            from datetime import date
            query=query.filter(document__date__lte=date.fromisoformat(through))
        rows=[{'id':e.pk,'number':e.document.number,'date':e.document.date,'location':e.location_id,'debit':e.debit,'credit':e.credit,'amount':e.debit-e.credit} for e in query.order_by('document__date','id')[:5000]]
        return response({'results':rows,'truncated':query.count()>5000})

class AuditAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request); ctx.require('audit.view')
        query=AuditEvent.objects.filter(business=ctx.business)
        if not ctx.membership.all_locations:
            ids=[str(pk) for pk in document_scope(ctx).values_list('pk',flat=True)]
            query=query.filter(Q(user=request.user)|Q(action__startswith='post:',target__in=ids))
        result=[]
        for item in query.order_by('-id')[:200]:
            row=serialize_model(item)
            if item.details.get('resource')=='employees' and not can(ctx,'payroll.view','payroll.post'):
                row['details']={'resource':'employees','redacted':True}
            else: row['details']=redact(ctx,item.details)
            result.append(row)
        return response({'results':result})

class AttachmentAPI(Boundary):
    def get(self,request,pk):
        ctx=self.ctx(request); item=get_obj(ctx,Attachment,pk); doc_permission(ctx,item.document)
        return FileResponse(item.file.open('rb'),as_attachment=True,filename=item.filename,content_type='application/octet-stream')
    def post(self,request):
        ctx=self.ctx(request); doc=get_obj(ctx,Document,request.data.get('document')); doc_permission(ctx,doc)
        ctx.require('attachments.create')
        upload=request.FILES.get('file')
        if not upload or upload.size>10*1024*1024: raise ValidationError('Select a supported file no larger than 10 MB.')
        suffix=Path(upload.name).suffix.lower()
        if suffix not in {'.pdf','.png','.jpg','.jpeg','.txt','.csv'}: raise ValidationError('Supported attachments: PDF, PNG, JPG, TXT, CSV.')
        first=upload.read(16); upload.seek(0)
        if suffix=='.pdf' and not first.startswith(b'%PDF'): raise ValidationError('Invalid PDF.')
        if suffix=='.png' and not first.startswith(b'\x89PNG\r\n'): raise ValidationError('Invalid PNG.')
        if suffix in {'.jpg','.jpeg'} and not first.startswith(b'\xff\xd8'): raise ValidationError('Invalid JPEG.')
        import uuid
        filename=Path(upload.name).name; upload.name=uuid.uuid4().hex+suffix
        item=Attachment.objects.create(business=ctx.business,document=doc,file=upload,filename=filename,uploaded_by=request.user)
        AuditEvent.objects.create(business=ctx.business,user=request.user,action='attachment.upload',target=str(item.pk))
        return response({'id':item.pk,'filename':filename},201)

class SecurityAPI(Boundary):
    def post(self,request,action):
        if action=='password':
            if not request.user.check_password(request.data.get('current_password','')): raise ValidationError('Current password is incorrect.')
            new=request.data.get('new_password',''); password_validation.validate_password(new,request.user)
            request.user.set_password(new); request.user.save()
            logout(request); return response({'ok':True})
        if action=='revoke_sessions':
            for session in Session.objects.filter(expire_date__gt=timezone.now()):
                if str(session.get_decoded().get('_auth_user_id'))==str(request.user.pk): session.delete()
            return response({'ok':True})
        if action=='mfa_setup':
            device,_=TOTPDevice.objects.get_or_create(user=request.user,name='Authenticator',confirmed=False)
            import base64
            import qrcode
            from qrcode.image.svg import SvgPathImage
            svg=qrcode.make(device.config_url,image_factory=SvgPathImage).to_string()
            return response({'configuration_url':device.config_url,'qr_data_url':'data:image/svg+xml;base64,'+base64.b64encode(svg).decode('ascii')})
        if action=='mfa_confirm':
            device=TOTPDevice.objects.filter(user=request.user,confirmed=False,name='Authenticator').first()
            if not device or not device.verify_token(request.data.get('otp','')): raise ValidationError('Invalid authenticator code.')
            device.confirmed=True; device.save(); otp_login(request,device)
            return response({'ok':True})
        raise ValidationError('Unsupported security action.')

class BusinessSettingsAPI(Boundary):
    @transaction.atomic
    def patch(self,request):
        ctx=self.ctx(request); ctx.require('settings.manage')
        ctx.business=Business.objects.select_for_update().get(pk=ctx.business.pk)
        fields={k:v for k,v in request.data.items() if k in ('name','manufacturing_mode','settings')}
        if 'settings' in fields and not isinstance(fields['settings'],dict): raise ValidationError('Business settings must be an object.')
        if 'settings' in fields and fields['settings'].get('calendar_policies',[])!=ctx.business.settings.get('calendar_policies',[]):
            raise ValidationError('Use the audited business-calendar policy workflow; recorded calendar history cannot be overwritten.')
        if 'settings' in fields and 'print_profile' in fields['settings']:
            from .growth import validate_print_profile
            validate_print_profile(fields['settings']['print_profile'])
        if 'settings' in fields and fields['settings'].get('lot_tracking',False)!=ctx.business.settings.get('lot_tracking',False):
            raise ValidationError('Use the controlled lot-tracking activation workflow after assigning existing stock; disabling recorded traceability requires operator review.')
        if 'settings' in fields and fields['settings'].get('separate_approver',True)!=ctx.business.settings.get('separate_approver',True): ctx.require('approvals.manage')
        for k,v in fields.items(): setattr(ctx.business,k,v)
        ctx.business.full_clean(); ctx.business.save()
        AuditEvent.objects.create(business=ctx.business,user=request.user,action='business.settings',details={'fields':list(fields)})
        return response({'ok':True})

class SetupAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request);ctx.require('settings.manage')
        biz=ctx.business
        items=[
            {'key':'locations','label':'موقعیت‌ها و گدام‌ها / Locations and warehouses','ready':Location.objects.filter(business=biz).exists() and Warehouse.objects.filter(business=biz).exists()},
            {'key':'accounts','label':'حساب‌های کنترلی / Chart of accounts','ready':Account.objects.filter(business=biz).count()>=20},
            {'key':'products','label':'محصولات و واحدها / Products and units','ready':Product.objects.filter(business=biz).exists()},
            {'key':'permissions','label':'دسترسی کاربران / User assignments','ready':Membership.objects.filter(business=biz,active=True).exists()},
            {'key':'opening','label':'بررسی مانده آغازین واقعی / Reviewed real opening balances','ready':bool(biz.settings.get('setup_reviews',{}).get('opening'))},
            {'key':'costing','label':'بررسی هزینه و سربار / Costing policy review','ready':bool(biz.settings.get('setup_reviews',{}).get('costing'))},
            {'key':'taxes','label':'بررسی مالیات قابل اجرا / Applicable tax review','ready':bool(biz.settings.get('setup_reviews',{}).get('taxes'))},
            {'key':'backups','label':'تعیین مسئول نسخه پشتیبان / Backup responsibility','ready':bool(biz.settings.get('setup_reviews',{}).get('backups'))},
        ]
        return response({'items':items,'reviews':biz.settings.get('setup_reviews',{}),'demo':bool(biz.settings.get('demo')),'note':'Checklist acknowledgments are internal reviews, not legal or accounting certification. Demo balances do not establish real opening balances.'})
    @transaction.atomic
    def post(self,request):
        ctx=self.ctx(request);ctx.require('settings.manage')
        area=request.data.get('area')
        if area not in ('opening','costing','taxes','backups'): raise ValidationError('Select a review area.')
        if area in ('opening','costing','taxes'): ctx.require('accounting.manage')
        reason=str(request.data.get('reason','')).strip()
        if not reason: raise ValidationError('Record the review reference and responsible person.')
        reviews={**ctx.business.settings.get('setup_reviews',{}),area:{'by':request.user.pk,'at':timezone.now().isoformat(),'reason':reason}}
        ctx.business.settings={**ctx.business.settings,'setup_reviews':reviews};ctx.business.save(update_fields=['settings'])
        AuditEvent.objects.create(business=ctx.business,user=request.user,action='setup.review',target=area,details={'reason':reason})
        return response({'ok':True})

class BusinessesAPI(Boundary):
    @transaction.atomic
    def post(self,request):
        ctx=self.ctx(request); ctx.require('businesses.create')
        name=str(request.data.get('name','')).strip(); slug=str(request.data.get('slug','')).strip()
        if not name or not slug: raise ValidationError('Business name and unique slug are required.')
        entity_id=request.data.get('legal_entity')
        if entity_id:
            if not Business.objects.filter(legal_entity_id=entity_id,membership__user=request.user,membership__active=True).exists(): raise PermissionDenied('Legal entity is outside your assigned businesses.')
            entity=LegalEntity.objects.get(pk=entity_id)
        else: entity=LegalEntity.objects.create(name=request.data.get('legal_name') or name)
        business=Business(name=name,slug=slug,legal_entity=entity,manufacturing_mode=request.data.get('manufacturing_mode','actual'),settings={'demo':bool(ctx.business.settings.get('demo'))})
        business.full_clean(); business.save()
        from .seed import bootstrap
        bootstrap(business)
        Membership.objects.create(business=business,user=request.user,role='Owner',permissions=['*'],all_locations=True,product_lines=['sponge','adhesive','shared'],approval_limit=Decimal('1000000'))
        if request.data.get('location_name'):
            from .master_names import prepare_name_payload
            loc=Location(business=business,code='MAIN')
            names={'name':str(request.data['location_name'])};prepare_name_payload(loc,names)
            for key,value in names.items():setattr(loc,key,value)
            loc.full_clean();loc.save()
            warehouse=Warehouse(business=business,location=loc)
            names={'name':str(request.data.get('warehouse_name') or 'گدام اصلی')};prepare_name_payload(warehouse,names)
            for key,value in names.items():setattr(warehouse,key,value)
            warehouse.full_clean();warehouse.save()
        AuditEvent.objects.create(business=business,user=request.user,action='business.create',target=str(business.pk))
        return response({'id':business.pk,'name':business.name,'slug':business.slug},201)

class HealthAPI(APIView):
    permission_classes=[AllowAny]
    def get(self,request):
        from django.db import connection,DatabaseError
        from .installation import installation_id,running_release
        try:
            with connection.cursor() as c:c.execute('SELECT 1')
            result=response({'status':'ok','database':'postgresql','installation_id':installation_id(),'running_release':running_release()})
        except DatabaseError:
            result=response({'status':'unavailable','database':'unavailable','installation_id':installation_id(),'running_release':running_release()},503)
        result['Cache-Control']='no-store'
        return result


class BlockLabelAPI(Boundary):
    def get(self,request,pk):
        from .labels import block_label
        from .error_localization import language_for
        # A print navigation cannot send the app's Accept-Language override.
        language=UserPreference.objects.filter(user=request.user).values_list('language',flat=True).first() or language_for(request)
        return HttpResponse(block_label(self.ctx(request),pk,language),content_type='text/html; charset=utf-8')

class SchemaAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request)
        return response({'operations':[{'action':name,'permission':value[0]} for name,value in registry().items() if ctx.has(value[0])],'decimal_format':'string','currency':'AFN','unsupported':['partial_footprint_cut','cross_currency_settlement','nonmonetary_foreign_goods_advances','offline_finalization','historical_cost_replay','statutory_consolidation']})

class DraftPostAPI(Boundary):
    @transaction.atomic
    def post(self,request,pk):
        ctx=self.ctx(request); Business.objects.select_for_update().get(pk=ctx.business.pk)
        source=get_obj(ctx,Document,pk); doc_permission(ctx,source)
        ctx.require('drafts.create')
        if source.state=='converted':
            return response({'document':document_data(ctx,get_obj(ctx,Document,source.result['posted_document']))})
        if source.state!='draft': raise ValidationError('Only a draft can be posted.')
        from .capture import validate_draft_source
        validate_draft_source(ctx,source)
        posted=execute(ctx,source.kind,source.data,'draft-post-'+str(source.pk))
        source.state='converted'; source.result={'posted_document':posted.pk}; source.save(update_fields=['state','result'])
        return response({'document':document_data(ctx,posted),'result':public_result(ctx,posted,posted.result)},201)

class ImportAPI(Boundary):
    def get(self,request,resource):
        ctx=self.ctx(request); ctx.require('settings.manage')
        from .administration import IMPORT_FIELDS
        if resource not in IMPORT_FIELDS: raise ValidationError('Supported imports: products, parties.')
        return response({'resource':resource,'columns':IMPORT_FIELDS[resource],'instructions':'POST CSV file with preview=true; inspect errors; repeat with preview=false and Idempotency-Key to commit atomically.'})
    def post(self,request,resource):
        from .administration import prepare_import
        ctx=self.ctx(request); ctx.require('settings.manage')
        upload=request.FILES.get('file')
        if not upload or upload.size>1024*1024: raise ValidationError('Provide a CSV file no larger than 1 MB.')
        try: text=upload.read().decode('utf-8-sig')
        except UnicodeDecodeError: raise ValidationError('CSV must use UTF-8 encoding.')
        rows=list(csv.DictReader(io.StringIO(text)))
        if any(not isinstance(value,(str,type(None))) for row in rows for value in row.values()): raise ValidationError('CSV row has more values than header columns.')
        if request.data.get('preview','true').lower()!='false':
            prepared,errors=prepare_import(ctx,resource,rows)
            return response({'rows':prepared,'errors':errors,'count':len(prepared)})
        # Let execute compare the unchanged request before revalidating unique
        # item codes: an identical retry must not fail as a duplicate import.
        canonical=[{key:(value or '').strip() for key,value in row.items()} for row in rows]
        doc=execute(ctx,'catalog_import',{'resource':resource,'rows':canonical},request.headers.get('Idempotency-Key'))
        return response({'document':document_data(ctx,doc),'result':doc.result},201)

class PrintAPI(Boundary):
    def get(self,request,pk):
        from django.template.loader import render_to_string
        ctx=self.ctx(request); ctx.require('documents.print')
        doc=get_obj(ctx,Document,pk); data=document_data(ctx,doc)
        from .document_print import context as print_context, number, TITLES
        from .localization import printed_date
        from .print_settings import profile_for
        from .print_profiles import effective
        options=effective(profile_for(ctx.business),doc.kind,request.query_params)
        view=print_context(ctx.business,doc,data,request.user,compact=options['compact'],copy=request.query_params.get('copy')=='1')
        if doc.reference_id:
            # A printed reference must obey the same document scope as a link.
            doc_permission(ctx,doc.reference)
            view['source_number']=doc.reference.number
        incoming=doc.kind in ('sale','purchase_bill','opening_receivable','opening_payable') or (doc.kind in ('expense_post','asset_acquire') and doc.party_id)
        query=Allocation.objects.filter(invoice=doc) if incoming else Allocation.objects.filter(document=doc)
        allocations=[]
        for allocation in query.select_related('document','invoice').order_by('document__date','id'):
            target=allocation.document if incoming else allocation.invoice
            doc_permission(ctx,target)
            allocations.append({'number':target.number,'date':printed_date(target.date,request.user),'amount_display':number(allocation.amount,True),'balance_display':number(outstanding(target),True) if not incoming else '', 'kind_label':('نقد هنگام فروش / Cash at sale' if incoming and target.pk==doc.pk and doc.kind=='sale' else ' / '.join(TITLES.get(target.kind,('',target.kind))))})
        view['allocations']=allocations
        view['allocation_balances']=not incoming
        if incoming:
            view['allocations_label']='رویدادهای تسویه این بل / Invoice settlement history'
            view['allocation_reference_label']='شماره سند / Document number'
            settled=sum((allocation.amount for allocation in query),Decimal('0'))
            view['total_rows'].append(('مجموع تخصیص تسویه / Total settlement allocations',number(settled,True)))
        from .print_copy import apply
        apply(view,options)
        html=render_to_string('document.html',view)
        AuditEvent.objects.create(business=ctx.business,user=request.user,action='document.print',target=str(doc.pk),details={
            'event':'print_view_generated','physical_print_confirmed':False,'family':options['family'],'language':options['language'],
            'paper':options['paper'],'margin_mm':options['margin_mm'],'printer_profile':options['printer'],'copy':view['copy'],
            'content_sha256':hashlib.sha256(html.encode('utf8')).hexdigest(),
            'profile_sha256':hashlib.sha256(json.dumps(options['profile'],sort_keys=True,ensure_ascii=False).encode('utf8')).hexdigest()})
        return HttpResponse(html,content_type='text/html; charset=utf-8')

class ExportAPI(Boundary):
    def get(self,request,name):
        from .reports import report
        ctx=self.ctx(request); ctx.require('reports.export')
        table=report(ctx,name,dict(request.query_params.items()))
        if name=='employee_statement':
            from .employee_reports import employee_statement
            table=employee_statement(ctx,dict(request.query_params.items()),all_rows=True)
        rows=table.get('rows',[]); columns=table.get('columns',[])
        if table.get('comparative') and name in {'profit_loss','balance_sheet','changes_equity'}:
            previous={row['account']:row for row in table['comparative']['rows']}
            keys_now={row['account'] for row in rows}
            rows=[{**row,'comparison_amount':previous.get(row['account'],{}).get('amount','0')} for row in rows]
            rows += [{**row,'amount':'0','comparison_amount':row['amount']} for key,row in previous.items() if key not in keys_now]
            columns=[*columns,{'key':'comparison_amount','label':'Comparative amount — '+table['comparative']['as_of']}]
        keys=[c['key'] for c in columns] or (list(rows[0]) if rows else [])
        buf=io.StringIO(); writer=csv.writer(buf)
        def cell(v):
            text=str(v if v is not None else '')
            return "'"+text if text[:1] in ('=','+','-','@','\t','\r') else text
        writer.writerow([cell(c.get('label',c['key'])) for c in columns] if columns else keys)
        for row in rows: writer.writerow([cell(row.get(key,'')) for key in keys])
        AuditEvent.objects.create(business=ctx.business,user=request.user,action='report.export',target=name,details={'rows':len(rows)})
        result=HttpResponse('\ufeff'+buf.getvalue(),content_type='text/csv; charset=utf-8')
        result['Content-Disposition']=f'attachment; filename="{name}.csv"'
        return result

class ApprovalsAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request)
        query=document_scope(ctx).filter(state='requested').order_by('-id')
        results=[]
        for doc in query:
            permission=registry().get(doc.kind,('documents.view',))[0]
            if doc.created_by_id==request.user.pk or ctx.has(permission.split('.')[0]+'.approve'):
                try: results.append(document_data(ctx,doc))
                except PermissionDenied: continue
        return response({'results':results})
    @transaction.atomic
    def post(self,request,pk=None):
        ctx=self.ctx(request)
        if pk:
            Business.objects.select_for_update().get(pk=ctx.business.pk)
            source=get_obj(ctx,Document,pk); doc_permission(ctx,source)
            permission=registry()[source.kind][0]
            ctx.require(permission.split('.')[0]+'.approve')
            if source.state=='approved': return response({'document':document_data(ctx,get_obj(ctx,Document,source.result['posted_document']))})
            if source.state!='requested': raise ValidationError('This approval request is no longer open.')
            if source.created_by_id==request.user.pk and ctx.business.settings.get('separate_approver',True):
                raise PermissionDenied('A different authorized user must approve this request.')
            if request.data.get('reject'):
                if not request.data.get('reason'): raise ValidationError('A rejection requires a reason.')
                source.state='rejected'; source.result={'reason':str(request.data['reason'])}; source.save(update_fields=['state','result'])
                AuditEvent.objects.create(business=ctx.business,user=request.user,action='approval.reject',target=str(source.pk))
                return response({'ok':True})
            ctx.approval_source=source.pk
            approved=execute(ctx,source.kind,source.data,'approval-'+str(source.pk))
            source.state='approved'; source.result={'posted_document':approved.pk,'approved_by':request.user.pk}; source.save(update_fields=['state','result'])
            AuditEvent.objects.create(business=ctx.business,user=request.user,action='approval.approve',target=str(source.pk),details={'posted_document':approved.pk,'requester':source.created_by_id})
            return response({'document':document_data(ctx,approved),'result':public_result(ctx,approved,approved.result)},201)
        kind=request.data.get('kind'); payload=request.data.get('data')
        if kind not in registry() or not isinstance(payload,dict): raise ValidationError('Select a supported action and payload.')
        ctx.require(registry()[kind][0])
        import uuid
        doc=Document(business=ctx.business,kind=kind,number='APP-'+uuid.uuid4().hex[:16],state='requested',date=payload.get('date') or timezone.localdate(),data=payload,idempotency_key='approval-request-'+uuid.uuid4().hex,request_hash=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),created_by=request.user)
        if payload.get('location'): doc.location=get_obj(ctx,Location,payload['location'])
        if payload.get('warehouse'): doc.warehouse=get_obj(ctx,Warehouse,payload['warehouse']); doc.location=doc.warehouse.location
        for item in payload.get('lines',[])+payload.get('inputs',[])+payload.get('outputs',[]):
            if item.get('product'): get_obj(ctx,Product,item['product'])
        doc.product_lines=sorted(ctx.lines); doc.full_clean(); doc.save()
        AuditEvent.objects.create(business=ctx.business,user=request.user,action='approval.request',target=str(doc.pk))
        return response({'document':document_data(ctx,doc)},201)
