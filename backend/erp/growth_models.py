"""Operational extensions. Authoritative accounting/stock stays in Entry/StockMovement."""
from django.conf import settings
from django.db import models
from django.db.models import Q
from .models import Owned

class UserPreference(models.Model):
    user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    language=models.CharField(max_length=2,default='fa',choices=[('fa','Dari'),('ps','Pashto'),('en','English')])
    calendar=models.CharField(max_length=12,default='jalali',choices=[('gregorian','Gregorian'),('jalali','Jalali')])

class CollectionTask(Owned):
    invoice=models.ForeignKey('erp.Document',on_delete=models.PROTECT)
    assignee=models.ForeignKey('erp.Membership',null=True,blank=True,on_delete=models.PROTECT)
    due_date=models.DateField()
    promised_amount=models.DecimalField(max_digits=20,decimal_places=2)
    state=models.CharField(max_length=16,default='open',choices=[('open','Open'),('kept','Kept'),('broken','Broken'),('cancelled','Cancelled')])
    note=models.TextField(blank=True)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    closed_by=models.ForeignKey('erp.Document',null=True,blank=True,on_delete=models.PROTECT,related_name='+')
    class Meta:
        indexes=[models.Index(fields=['business','state','due_date'])]
        constraints=[models.CheckConstraint(condition=Q(promised_amount__gt=0),name='collection_positive')]

class CollectionNote(Owned):
    task=models.ForeignKey(CollectionTask,on_delete=models.PROTECT,related_name='notes')
    document=models.OneToOneField('erp.Document',on_delete=models.PROTECT)
    outcome=models.CharField(max_length=20)
    note=models.TextField()
    next_date=models.DateField(null=True,blank=True)

class ReminderMessage(Owned):
    task=models.ForeignKey(CollectionTask,on_delete=models.PROTECT)
    channel=models.CharField(max_length=12,choices=[('manual','Manual'),('sms','SMS'),('whatsapp','WhatsApp')])
    recipient=models.CharField(max_length=50)
    body=models.TextField()
    authorized_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    source=models.OneToOneField('erp.Document',on_delete=models.PROTECT)
    state=models.CharField(max_length=16,default='queued')
    attempts=models.PositiveIntegerField(default=0)
    last_error=models.CharField(max_length=250,blank=True)
    provider_reference=models.CharField(max_length=150,blank=True)
    sent_at=models.DateTimeField(null=True,blank=True)

class ReorderPolicy(Owned):
    warehouse=models.ForeignKey('erp.Warehouse',on_delete=models.PROTECT)
    product=models.ForeignKey('erp.Product',on_delete=models.PROTECT)
    profile=models.CharField(max_length=100,blank=True)
    minimum=models.DecimalField(max_digits=24,decimal_places=6,default=0)
    target=models.DecimalField(max_digits=24,decimal_places=6)
    safety_stock=models.DecimalField(max_digits=24,decimal_places=6,default=0)
    daily_usage=models.DecimalField(max_digits=24,decimal_places=6,default=0)
    lead_days=models.PositiveSmallIntegerField(default=0)
    supplier=models.ForeignKey('erp.Party',null=True,blank=True,on_delete=models.PROTECT)
    active=models.BooleanField(default=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['business','warehouse','product','profile'],name='reorder_policy_scope'),models.CheckConstraint(condition=Q(minimum__gte=0,target__gt=0,safety_stock__gte=0,daily_usage__gte=0),name='reorder_amounts_positive')]

class PurchaseRequest(Owned):
    policy=models.ForeignKey(ReorderPolicy,on_delete=models.PROTECT)
    quantity=models.DecimalField(max_digits=24,decimal_places=6)
    source=models.OneToOneField('erp.Document',on_delete=models.PROTECT)
    order=models.ForeignKey('erp.Document',null=True,blank=True,on_delete=models.PROTECT,related_name='+')
    state=models.CharField(max_length=16,default='open')

class WorkCenter(Owned):
    name=models.CharField(max_length=150)
    location=models.ForeignKey('erp.Location',on_delete=models.PROTECT)
    daily_minutes=models.PositiveIntegerField(default=480)
    active=models.BooleanField(default=True)
    class Meta: constraints=[models.UniqueConstraint(fields=['business','name'],name='workcenter_name_scope')]

class WorkOrder(Owned):
    number=models.CharField(max_length=60)
    product=models.ForeignKey('erp.Product',on_delete=models.PROTECT)
    warehouse=models.ForeignKey('erp.Warehouse',on_delete=models.PROTECT)
    work_center=models.ForeignKey(WorkCenter,on_delete=models.PROTECT)
    order=models.ForeignKey('erp.Document',null=True,blank=True,on_delete=models.PROTECT,related_name='+')
    planned_quantity=models.DecimalField(max_digits=24,decimal_places=6)
    scheduled_date=models.DateField()
    planned_minutes=models.PositiveIntegerField()
    state=models.CharField(max_length=20,default='planned')
    notes=models.TextField(blank=True)
    source=models.OneToOneField('erp.Document',on_delete=models.PROTECT)
    class Meta: constraints=[models.UniqueConstraint(fields=['business','number'],name='workorder_number_scope')]

class JobCard(Owned):
    work_order=models.ForeignKey(WorkOrder,on_delete=models.PROTECT,related_name='job_cards')
    employee=models.ForeignKey('erp.Employee',null=True,blank=True,on_delete=models.PROTECT)
    operation=models.CharField(max_length=150)
    minutes=models.PositiveIntegerField()
    date=models.DateField()
    note=models.TextField(blank=True)
    source=models.OneToOneField('erp.Document',on_delete=models.PROTECT)

class WorkProduction(Owned):
    work_order=models.ForeignKey(WorkOrder,on_delete=models.PROTECT,related_name='production_links')
    document=models.OneToOneField('erp.Document',on_delete=models.PROTECT)

class CutPlan(Owned):
    warehouse=models.ForeignKey('erp.Warehouse',on_delete=models.PROTECT)
    product=models.ForeignKey('erp.Product',on_delete=models.PROTECT)
    profile=models.CharField(max_length=100)
    allocations=models.JSONField(default=list)
    reservation=models.ForeignKey('erp.Document',null=True,blank=True,on_delete=models.PROTECT,related_name='+')
    state=models.CharField(max_length=16,default='planned')
    source=models.OneToOneField('erp.Document',on_delete=models.PROTECT)
    completed_by=models.ForeignKey('erp.Document',null=True,blank=True,on_delete=models.PROTECT,related_name='+')

class BinLocation(Owned):
    warehouse=models.ForeignKey('erp.Warehouse',on_delete=models.PROTECT)
    code=models.CharField(max_length=50)
    description=models.CharField(max_length=200,blank=True)
    active=models.BooleanField(default=True)
    class Meta: constraints=[models.UniqueConstraint(fields=['business','warehouse','code'],name='bin_code_scope')]

class BlockPlacement(Owned):
    block=models.OneToOneField('erp.Block',on_delete=models.PROTECT)
    bin=models.ForeignKey(BinLocation,on_delete=models.PROTECT)
    source=models.ForeignKey('erp.Document',on_delete=models.PROTECT)

class DeliveryConfirmation(Owned):
    invoice=models.OneToOneField('erp.Document',on_delete=models.PROTECT)
    recipient=models.CharField(max_length=200)
    received_at=models.DateTimeField()
    note=models.TextField(blank=True)
    source=models.OneToOneField('erp.Document',on_delete=models.PROTECT,related_name='+')

class InspectionTemplate(Owned):
    name=models.CharField(max_length=150)
    product=models.ForeignKey('erp.Product',on_delete=models.PROTECT)
    criteria=models.JSONField(default=list)
    active=models.BooleanField(default=True)

class QualityInspection(Owned):
    template=models.ForeignKey(InspectionTemplate,on_delete=models.PROTECT)
    block=models.ForeignKey('erp.Block',null=True,blank=True,on_delete=models.PROTECT)
    batch=models.ForeignKey('erp.Document',null=True,blank=True,on_delete=models.PROTECT,related_name='+')
    measurements=models.JSONField(default=dict)
    outcome=models.CharField(max_length=12)
    source=models.OneToOneField('erp.Document',on_delete=models.PROTECT)
    note=models.TextField(blank=True)

class MaterialLot(Owned):
    code=models.CharField(max_length=100)
    product=models.ForeignKey('erp.Product',on_delete=models.PROTECT)
    supplier=models.ForeignKey('erp.Party',null=True,blank=True,on_delete=models.PROTECT)
    expiry_date=models.DateField(null=True,blank=True)
    state=models.CharField(max_length=12,default='released')
    class Meta: constraints=[models.UniqueConstraint(fields=['business','code','product'],name='material_lot_code_scope')]

class LotMovement(Owned):
    lot=models.ForeignKey(MaterialLot,on_delete=models.PROTECT)
    warehouse=models.ForeignKey('erp.Warehouse',on_delete=models.PROTECT)
    document=models.ForeignKey('erp.Document',on_delete=models.PROTECT)
    quantity=models.DecimalField(max_digits=24,decimal_places=6)

class BudgetLine(Owned):
    period=models.CharField(max_length=7)
    account=models.ForeignKey('erp.Account',on_delete=models.PROTECT)
    location=models.ForeignKey('erp.Location',on_delete=models.PROTECT)
    line=models.CharField(max_length=16,default='shared')
    amount=models.DecimalField(max_digits=20,decimal_places=2)
    class Meta: constraints=[models.UniqueConstraint(fields=['business','period','account','location','line'],name='budget_line_scope'),models.CheckConstraint(condition=Q(amount__gte=0),name='budget_amount_nonnegative')]

class ForecastItem(Owned):
    date=models.DateField()
    location=models.ForeignKey('erp.Location',on_delete=models.PROTECT)
    direction=models.CharField(max_length=4,choices=[('in','In'),('out','Out')])
    amount=models.DecimalField(max_digits=20,decimal_places=2)
    description=models.CharField(max_length=250)
    state=models.CharField(max_length=12,default='planned')
    source=models.OneToOneField('erp.Document',on_delete=models.PROTECT)

class Equipment(Owned):
    name=models.CharField(max_length=150)
    work_center=models.ForeignKey(WorkCenter,on_delete=models.PROTECT)
    asset=models.ForeignKey('erp.Asset',null=True,blank=True,on_delete=models.PROTECT)
    service_interval_days=models.PositiveIntegerField(default=30)
    next_service=models.DateField()
    active=models.BooleanField(default=True)

class MaintenanceJob(Owned):
    equipment=models.ForeignKey(Equipment,on_delete=models.PROTECT)
    due_date=models.DateField()
    reason=models.TextField()
    downtime_minutes=models.PositiveIntegerField(default=0)
    state=models.CharField(max_length=16,default='open')
    source=models.OneToOneField('erp.Document',on_delete=models.PROTECT)
    completed_by=models.ForeignKey('erp.Document',null=True,blank=True,on_delete=models.PROTECT,related_name='+')

class CustomerPrice(Owned):
    party=models.ForeignKey('erp.Party',on_delete=models.PROTECT)
    product=models.ForeignKey('erp.Product',on_delete=models.PROTECT)
    profile=models.CharField(max_length=100,blank=True)
    unit_price=models.DecimalField(max_digits=20,decimal_places=6)
    effective_from=models.DateField()
    effective_to=models.DateField(null=True,blank=True)

class PortalGrant(Owned):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    party=models.ForeignKey('erp.Party',on_delete=models.PROTECT)
    active=models.BooleanField(default=True)
    class Meta: constraints=[models.UniqueConstraint(fields=['business','user'],name='portal_user_scope')]
