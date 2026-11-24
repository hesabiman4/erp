"""Explicit capability catalog and guarded, auditable role assignments.

Roles materialize into the existing membership permissions: every existing
service remains authoritative, including locations, product lines and limits.
No accounting or stock writes occur here.
"""
import ast
import re
from pathlib import Path
from functools import lru_cache
from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from .api import Boundary,response,serialize_model
from .core import Context,D,get_obj,registry
from .models import AccessRole,AuditEvent,Business,Membership,Location

MODULES={'sales':'فروش و مشتریان','purchases':'خرید و تأمین‌کنندگان','inventory':'موجودی و انبار','production':'تولید','transfers':'انتقالات','finance':'صندوق و مصارف','payroll':'کارمندان و معاشات','accounting':'حسابداری','reports':'گزارش‌ها','documents':'اسناد','drafts':'پیش‌نویس‌ها','attachments':'پیوست‌ها','users':'کاربران و دسترسی','settings':'تنظیمات کسب‌وکار','cost':'بهای تمام‌شده','consumption':'مصرف واقعی مواد','bom':'فرمول تولید','audit':'رویدادها و بررسی','approvals':'تأیید معاملات','businesses':'کسب‌وکارها','crm':'پیگیری مشتریان','capture':'خواندن عکس سند','cash_shifts':'نوبت صندوق','statements':'صورت‌حساب بانک','delivery':'تحویل مشتری','jobs':'پروژه‌ها','maintenance':'ترمیم تجهیزات','messaging':'پیام مشتری','quality':'کنترول کیفیت','runtime':'مدیریت سیستم'}
# Explicit non-operation capabilities. The registry adds all executable service
# permissions, so future services cannot silently disappear from the editor.
EXTRA='''purchases.terms_manage sales.credit_summary sales.credit_manage accounting.view accounting.manage approvals.manage approvals.override attachments.create audit.view bom.view businesses.create capture.view capture.upload capture.review cash_shifts.view cash_shifts.manage cash_shifts.self_review consumption.view cost.view crm.view crm.read_all documents.all_lines documents.cancel documents.print documents.view drafts.create drafts.manage finance.view finance.manage inventory.view inventory.raw inventory.count_self_review jobs.view maintenance.view payroll.view payroll.manage production.view production.cost purchases.view quality.view quality.recall_customers reports.view reports.export runtime.manage sales.view sales.credit sales.credit_override sales.discount sales.price settings.manage statements.view statements.import users.manage users.grant_all'''.split()

@lru_cache(maxsize=1)
def permission_codes():
    codes=set(EXTRA)|{'accounting.tax_view','accounting.tax_manage','accounting.tax_confirm','accounting.tax_override'}|{permission for permission,_ in registry().values()}
    # Include literal checked capabilities from the installed domain modules.
    # Restrict to known namespaces and permission-check calls, not audit labels.
    for file in Path(__file__).parent.glob('*.py'):
        if file.name=='access_control.py':continue
        for node in ast.walk(ast.parse(file.read_text(encoding='utf-8'))):
            if isinstance(node,ast.Call) and ((isinstance(node.func,ast.Attribute) and node.func.attr in ('has','require')) or (isinstance(node.func,ast.Name) and node.func.id=='can')):
                codes.update(arg.value for arg in node.args if isinstance(arg,ast.Constant) and isinstance(arg.value,str) and re.fullmatch(r'[a-z_]+\.[a-z_]+',arg.value) and arg.value.split('.')[0] in MODULES)
    return tuple(sorted(codes))

def permission_catalog(ctx):
    return [{'code':code,'module':code.split('.')[0],'action':code.split('.')[1], 'grantable':ctx.has('users.grant_all') or ctx.has(code),'operations':[name for name,(p,_) in registry().items() if p==code]} for code in permission_codes()]

def validate_grants(ctx,values):
    known={r['code'] for r in permission_catalog(ctx)}
    if not isinstance(values,list) or any(not isinstance(v,str) or (v not in known and v!='*' and v not in {m+'.*' for m in MODULES}) for v in values):
        raise ValidationError('Select valid application permissions.')
    if not ctx.has('users.grant_all') and any(not ctx.has(v) for v in values):raise PermissionDenied('You cannot grant privileges outside your own assignment.')
    return sorted(set(values))

def protect_membership(ctx,obj,previous=None):
    for loc in obj.location_ids:get_obj(ctx,Location,loc)
    validate_grants(ctx,obj.permissions)
    if not ctx.has('users.grant_all'):
        if obj.all_locations and not ctx.membership.all_locations:raise PermissionDenied('You cannot grant privileges outside your own assignment.')
        if not set(obj.location_ids).issubset(set(ctx.membership.location_ids)) and not ctx.membership.all_locations:raise PermissionDenied('You cannot grant privileges outside your own assignment.')
        if not set(obj.product_lines).issubset(set(ctx.membership.product_lines)) or obj.approval_limit>ctx.membership.approval_limit:raise PermissionDenied('You cannot grant product lines or approval limits beyond your own assignment.')
    if previous and previous.active and '*' in previous.permissions and (not obj.active or '*' not in obj.permissions):
        if not Membership.objects.filter(business=ctx.business,active=True,permissions__contains=['*']).exclude(pk=obj.pk).exists():
            raise ValidationError('Keep at least one active business owner with full access.')

class AccessControlAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request);ctx.require('users.manage')
        catalog=permission_catalog(ctx)
        members=[{**serialize_model(m),'username':m.user.username,'display_name':m.user.get_full_name() or m.user.username} for m in Membership.objects.filter(business=ctx.business).select_related('user')]
        return response({'modules':MODULES,'permissions':catalog,'roles':[serialize_model(r) for r in AccessRole.objects.filter(business=ctx.business).order_by('name')],'members':members,'can_grant_all':ctx.has('users.grant_all'),'locations':[{'id':l.pk,'name':l.name} for l in Location.objects.filter(business=ctx.business) if ctx.location_allowed(l.pk)],'actor':ctx.membership.pk})
    @transaction.atomic
    def post(self,request):
        ctx=self.ctx(request);ctx.require('users.manage');Business.objects.select_for_update().get(pk=ctx.business.pk)
        # Recheck after the business lock; a concurrent administrator may revoke.
        ctx=Context(request.user,ctx.business);ctx.require('users.manage');p=request.data;action=p.get('action')
        if action=='role':
            role=get_obj(ctx,AccessRole,p['id']) if p.get('id') else AccessRole(business=ctx.business)
            if role.pk and p.get('version')!=role.version:raise ValidationError('This role changed. Reload before saving.')
            grants=validate_grants(ctx,p.get('permissions',[]));name=str(p.get('name','')).strip()
            if not name:raise ValidationError('Enter a role name.')
            before=serialize_model(role) if role.pk else {};members=list(Membership.objects.filter(business=ctx.business,access_role=role)) if role.pk else []
            for member in members:
                previous=Membership.objects.get(pk=member.pk);member.permissions=grants;member.role=name;protect_membership(ctx,member,previous);member.full_clean();member.save(update_fields=['permissions','role'])
            role.name=name;role.permissions=grants;role.version+=1;role.full_clean();role.save()
            AuditEvent.objects.create(business=ctx.business,user=request.user,action='access.role',target=str(role.pk),details={'before':before,'after':serialize_model(role),'affected_memberships':[m.pk for m in members]})
            return response({'role':serialize_model(role),'affected_members':len(members)})
        if action!='member':raise ValidationError('Unknown access action.')
        member=get_obj(ctx,Membership,p['id']) if p.get('id') else Membership(business=ctx.business)
        previous=Membership.objects.get(pk=member.pk) if member.pk else None
        if previous and p.get('expected')!=serialize_model(previous):raise ValidationError('This assignment changed. Reload before saving.')
        if not member.pk:
            password=str(p.get('password',''));password_validation.validate_password(password);username=str(p.get('username','')).strip()
            if not username:raise ValidationError('Enter a username.')
            member.user=User.objects.create_user(username=username,password=password)
        if p.get('access_role'):
            role=get_obj(ctx,AccessRole,p['access_role']);member.access_role=role;member.role=role.name;member.permissions=list(role.permissions)
        else:
            member.access_role=None;member.role=str(p.get('role') or 'Custom');member.permissions=validate_grants(ctx,p.get('permissions',[]))
        for flag in ('all_locations','active'):
            if flag in p and not isinstance(p[flag],bool):raise ValidationError('Select a valid active or location option.')
        for key in ['all_locations','location_ids','product_lines','approval_limit','active']:
            if key in p:setattr(member,key,D(p[key]) if key=='approval_limit' else p[key])
        protect_membership(ctx,member,previous);member.full_clean();member.save()
        AuditEvent.objects.create(business=ctx.business,user=request.user,action='access.member',target=str(member.pk),details={'before':serialize_model(previous) if previous else {},'after':serialize_model(member)})
        return response({'member':serialize_model(member)},200 if previous else 201)
