from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

class LegalEntity(models.Model):
    name = models.CharField(max_length=200)
    registration = models.CharField(max_length=100, blank=True)

class Business(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    legal_entity = models.ForeignKey(LegalEntity, null=True, blank=True, on_delete=models.PROTECT)
    manufacturing_mode = models.CharField(max_length=12, default='actual', choices=[('actual','Actual consumption'),('bom','BOM assisted'),('trading','Trading')])
    currency = models.CharField(max_length=3, default='AFN')
    closed_through = models.DateField(null=True, blank=True)
    settings = models.JSONField(default=dict, blank=True)
    def __str__(self): return self.name

class Owned(models.Model):
    business = models.ForeignKey(Business, on_delete=models.PROTECT)
    class Meta: abstract = True
    def clean(self):
        super().clean()
        for field in self._meta.fields:
            if isinstance(field, models.ForeignKey) and field.name != 'business' and getattr(self, field.attname, None):
                related = getattr(self, field.name)
                if hasattr(related, 'business_id') and related.business_id != self.business_id:
                    raise ValidationError({field.name:'Referenced record belongs to another business.'})

class Location(Owned):
    name = models.CharField(max_length=200)
    name_fa = models.CharField(max_length=200,blank=True)
    name_en = models.CharField(max_length=200,blank=True)
    name_ps = models.CharField(max_length=200,blank=True)
    code = models.CharField(max_length=24)
    def clean(self):
        super().clean()
        from .master_names import validate_names
        validate_names(self)
    class Meta: constraints = [models.UniqueConstraint(fields=['business','code'],name='location_code_business')]
    def __str__(self): return self.name

class Warehouse(Owned):
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    name = models.CharField(max_length=200)
    name_fa = models.CharField(max_length=200,blank=True)
    name_en = models.CharField(max_length=200,blank=True)
    name_ps = models.CharField(max_length=200,blank=True)
    kind = models.CharField(max_length=16,default='store',choices=[('store','Store'),('floor','Production floor'),('transit','In transit')])
    def clean(self):
        super().clean()
        from .master_names import validate_names
        validate_names(self)
    def __str__(self): return self.name

class AccessRole(Owned):
    name = models.CharField(max_length=40)
    permissions = models.JSONField(default=list, blank=True)
    version = models.PositiveIntegerField(default=1)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['business','name'], name='access_role_business_name')]

class Membership(Owned):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=40,default='sales')
    access_role = models.ForeignKey(AccessRole, null=True, blank=True, on_delete=models.PROTECT)
    permissions = models.JSONField(default=list,blank=True)
    all_locations = models.BooleanField(default=False)
    location_ids = models.JSONField(default=list,blank=True)
    product_lines = models.JSONField(default=list,blank=True)
    approval_limit = models.DecimalField(max_digits=20,decimal_places=2,default=Decimal('0'))
    active = models.BooleanField(default=True)
    class Meta: constraints=[models.UniqueConstraint(fields=['business','user'],name='unique_membership')]
    def clean(self):
        super().clean()
        if not isinstance(self.permissions,list) or not all(isinstance(p,str) for p in self.permissions): raise ValidationError({'permissions':'Permissions must be a list of permission names.'})
        if not isinstance(self.product_lines,list) or not set(self.product_lines).issubset({'sponge','adhesive','shared'}): raise ValidationError({'product_lines':'Select valid product lines.'})
        if not isinstance(self.location_ids,list) or not all(isinstance(i,int) and not isinstance(i,bool) for i in self.location_ids): raise ValidationError({'location_ids':'Locations must be a list of numeric IDs.'})
        if self.approval_limit is not None and self.approval_limit<0: raise ValidationError({'approval_limit':'Approval limit cannot be negative.'})

class Product(Owned):
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=16,default='finished',choices=[('raw','Raw'),('finished','Finished'),('trim','Trim'),('scrap','Scrap'),('service','Service')])
    line = models.CharField(max_length=16,default='sponge',choices=[('sponge','Sponge'),('adhesive','Adhesive'),('shared','Shared')])
    unit = models.CharField(max_length=12,default='cm',choices=[('cm','cm thickness'),('kg','kg'),('each','Count')])
    price = models.DecimalField(max_digits=20,decimal_places=6,default=Decimal('0'))
    active = models.BooleanField(default=True)
    aliases = models.CharField(max_length=300,blank=True)
    class Meta: constraints=[models.UniqueConstraint(fields=['business','code'],name='product_code_business'),models.CheckConstraint(condition=Q(price__gte=0),name='product_price_positive')]
    def __str__(self): return self.name

class Party(Owned):
    kind = models.CharField(max_length=16,default='customer',choices=[('customer','Customer'),('supplier','Supplier')])
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=50,blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    group_name = models.CharField(max_length=80,blank=True)
    registration_number = models.CharField(max_length=80,blank=True)
    delivery_address = models.TextField(blank=True)
    contacts = models.JSONField(default=list,blank=True)
    credit_limit = models.DecimalField(max_digits=20,decimal_places=2,null=True,blank=True)
    payment_terms_days = models.PositiveIntegerField(default=0)
    credit_hold = models.BooleanField(default=False)
    block_overdue = models.BooleanField(default=False)
    def clean(self):
        super().clean()
        from .party_profiles import clean_contacts
        clean_contacts(self.contacts)
        if self.credit_limit is not None and self.credit_limit<0:raise ValidationError({'credit_limit':'Credit limit cannot be negative.'})
        if self.payment_terms_days is not None and self.payment_terms_days>365:raise ValidationError({'payment_terms_days':'Payment terms must be between 0 and 365 days.'})
    def __str__(self): return self.name

class Account(Owned):
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=16,choices=[('asset','Asset'),('liability','Liability'),('equity','Equity'),('income','Income'),('expense','Expense')])
    control = models.BooleanField(default=False)
    number = models.CharField(max_length=20,blank=True)
    statement_group = models.CharField(max_length=32,blank=True)
    class Meta: constraints=[models.UniqueConstraint(fields=['business','code'],name='account_code_business'),models.UniqueConstraint(fields=['business','number'],condition=~Q(number=''),name='account_number_business')]
    def clean(self):
        super().clean()
        from .chart import GROUP_CATEGORIES
        if self.statement_group and GROUP_CATEGORIES.get(self.statement_group)!=self.category:
            raise ValidationError({'statement_group':'Statement group must match the account category.'})

class Department(Owned):
    name = models.CharField(max_length=150)
    location = models.ForeignKey(Location,null=True,blank=True,on_delete=models.PROTECT)
    active = models.BooleanField(default=True)
    class Meta: constraints=[models.UniqueConstraint(fields=['business','name'],name='department_name_business')]

class Position(Owned):
    name = models.CharField(max_length=150)
    department = models.ForeignKey(Department,null=True,blank=True,on_delete=models.PROTECT)
    active = models.BooleanField(default=True)
    class Meta: constraints=[models.UniqueConstraint(fields=['business','name'],name='position_name_business')]

class Employee(Owned):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=40,blank=True)
    father_name = models.CharField(max_length=200,blank=True)
    phone = models.CharField(max_length=50,blank=True)
    email = models.EmailField(blank=True)
    national_id = models.CharField(max_length=80,blank=True)
    address = models.TextField(blank=True)
    emergency_name = models.CharField(max_length=200,blank=True)
    emergency_phone = models.CharField(max_length=50,blank=True)
    department = models.ForeignKey(Department,null=True,blank=True,on_delete=models.PROTECT)
    position = models.ForeignKey(Position,null=True,blank=True,on_delete=models.PROTECT)
    join_date = models.DateField(null=True,blank=True)
    end_date = models.DateField(null=True,blank=True)
    week_start = models.PositiveSmallIntegerField(default=5)
    payment_method = models.CharField(max_length=12,default='cash',choices=[('cash','Cash'),('bank','Bank')])
    bank_name = models.CharField(max_length=150,blank=True)
    bank_account = models.CharField(max_length=100,blank=True)
    location = models.ForeignKey(Location,on_delete=models.PROTECT)
    kind = models.CharField(max_length=16,default='monthly',choices=[('monthly','Monthly'),('weekly','Weekly'),('daily','Daily'),('hourly','Hourly'),('part_time','Part time'),('project','Project')])
    rate = models.DecimalField(max_digits=20,decimal_places=6,default=Decimal('0'))
    advance_limit = models.DecimalField(max_digits=20,decimal_places=2,default=Decimal('0'))
    active = models.BooleanField(default=True)
    terms = models.JSONField(default=dict,blank=True)
    class Meta: constraints=[models.UniqueConstraint(fields=['business','code'],condition=~Q(code=''),name='employee_code_business'),models.CheckConstraint(condition=Q(week_start__lte=6),name='employee_week_start'),models.CheckConstraint(condition=Q(rate__gte=0,advance_limit__gte=0),name='employee_amounts_nonnegative')]
    def clean(self):
        super().clean()
        if self.join_date and self.end_date and self.end_date<self.join_date:
            raise ValidationError({'end_date':'Employment end cannot precede joining.'})
        if not isinstance(self.terms,dict): raise ValidationError({'terms':'Contract terms must be an object.'})
        recovery=self.terms.get('max_recovery_per_payroll')
        if recovery is not None:
            try:
                amount=Decimal(str(recovery))
                if not amount.is_finite() or amount<0: raise ValueError()
            except (ValueError,ArithmeticError): raise ValidationError({'terms':'Advance recovery limit must be a nonnegative amount.'})
        if self.department_id and self.department.location_id and self.department.location_id!=self.location_id:
            raise ValidationError({'department':'Department belongs to a different location.'})
        if self.position_id and self.position.department_id and self.position.department_id!=self.department_id:
            raise ValidationError({'position':'Position must belong to the selected department.'})

class Document(Owned):
    kind = models.CharField(max_length=50)
    number = models.CharField(max_length=60)
    state = models.CharField(max_length=16,default='draft')
    date = models.DateField()
    location = models.ForeignKey(Location,null=True,blank=True,on_delete=models.PROTECT)
    warehouse = models.ForeignKey(Warehouse,null=True,blank=True,on_delete=models.PROTECT)
    party = models.ForeignKey(Party,null=True,blank=True,on_delete=models.PROTECT)
    employee = models.ForeignKey(Employee,null=True,blank=True,on_delete=models.PROTECT)
    reference = models.ForeignKey('self',null=True,blank=True,on_delete=models.PROTECT,related_name='children')
    amount = models.DecimalField(max_digits=20,decimal_places=2,default=Decimal('0'))
    data = models.JSONField(default=dict,blank=True)
    result = models.JSONField(default=dict,blank=True)
    product_lines = models.JSONField(default=list,blank=True)
    idempotency_key = models.CharField(max_length=100)
    request_hash = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True,blank=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['business','idempotency_key'],name='document_event_once'),models.UniqueConstraint(fields=['business','number'],name='document_number_once')]
        indexes=[models.Index(fields=['business','kind','date']),models.Index(fields=['business','kind','state','-id'],name='document_queue_lookup')]
    def save(self,*args,**kwargs):
        if self.pk and Document.objects.filter(pk=self.pk,state='posted').exists():
            raise ValidationError('Posted documents are immutable. Use a linked correction.')
        super().save(*args,**kwargs)

class Sequence(Owned):
    kind = models.CharField(max_length=50)
    value = models.PositiveBigIntegerField(default=0)
    class Meta: constraints=[models.UniqueConstraint(fields=['business','kind'],name='sequence_business_kind')]

class StockPool(Owned):
    product = models.ForeignKey(Product,on_delete=models.PROTECT)
    warehouse = models.ForeignKey(Warehouse,on_delete=models.PROTECT)
    profile = models.CharField(max_length=100,blank=True,default='')
    quantity = models.DecimalField(max_digits=24,decimal_places=6,default=Decimal('0'))
    value = models.DecimalField(max_digits=24,decimal_places=6,default=Decimal('0'))
    last_date = models.DateField(null=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['business','product','warehouse','profile'],name='stock_pool_unique'),models.CheckConstraint(condition=Q(quantity__gte=0),name='stock_quantity_nonnegative'),models.CheckConstraint(condition=Q(value__gte=0),name='stock_value_nonnegative')]

class Block(Owned):
    product = models.ForeignKey(Product,on_delete=models.PROTECT)
    warehouse = models.ForeignKey(Warehouse,on_delete=models.PROTECT)
    batch = models.ForeignKey(Document,null=True,blank=True,on_delete=models.PROTECT)
    parent = models.ForeignKey('self',null=True,blank=True,on_delete=models.PROTECT)
    code = models.CharField(max_length=80)
    length_mm = models.DecimalField(max_digits=18,decimal_places=3)
    width_mm = models.DecimalField(max_digits=18,decimal_places=3)
    initial_height_mm = models.DecimalField(max_digits=18,decimal_places=3)
    remaining_height_mm = models.DecimalField(max_digits=18,decimal_places=3)
    reserved_height_mm = models.DecimalField(max_digits=18,decimal_places=3,default=Decimal('0'))
    status = models.CharField(max_length=20,default='ready')
    profile = models.CharField(max_length=100,default='')
    class Meta:
        constraints=[models.UniqueConstraint(fields=['business','code'],name='block_code_unique'),models.CheckConstraint(condition=Q(remaining_height_mm__gte=0),name='block_nonnegative'),models.CheckConstraint(condition=Q(reserved_height_mm__gte=0)&Q(reserved_height_mm__lte=models.F('remaining_height_mm')),name='block_reservation_valid')]

class StockMovement(models.Model):
    document = models.ForeignKey(Document,on_delete=models.PROTECT,related_name='movements')
    pool = models.ForeignKey(StockPool,on_delete=models.PROTECT,related_name='movements')
    quantity = models.DecimalField(max_digits=24,decimal_places=6)
    value = models.DecimalField(max_digits=24,decimal_places=6)
    created_at = models.DateTimeField(auto_now_add=True)

class Entry(models.Model):
    document = models.ForeignKey(Document,on_delete=models.PROTECT,related_name='entries')
    account = models.ForeignKey(Account,on_delete=models.PROTECT)
    debit = models.DecimalField(max_digits=20,decimal_places=2,default=Decimal('0'))
    credit = models.DecimalField(max_digits=20,decimal_places=2,default=Decimal('0'))
    location = models.ForeignKey(Location,null=True,blank=True,on_delete=models.PROTECT)
    warehouse = models.ForeignKey(Warehouse,null=True,blank=True,on_delete=models.PROTECT)
    party = models.ForeignKey(Party,null=True,blank=True,on_delete=models.PROTECT)
    employee = models.ForeignKey(Employee,null=True,blank=True,on_delete=models.PROTECT)
    line = models.CharField(max_length=16,default='shared')
    class Meta: constraints=[models.CheckConstraint(condition=Q(debit__gte=0)&Q(credit__gte=0)&(Q(debit=0)|Q(credit=0)),name='entry_valid_sides')]

class Allocation(models.Model):
    document = models.ForeignKey(Document,on_delete=models.PROTECT,related_name='allocations')
    invoice = models.ForeignKey(Document,on_delete=models.PROTECT,related_name='settlements')
    amount = models.DecimalField(max_digits=20,decimal_places=2)
    class Meta: constraints=[models.CheckConstraint(condition=~Q(amount=0),name='allocation_nonzero')]

class BOM(Owned):
    product = models.ForeignKey(Product,on_delete=models.PROTECT)
    name = models.CharField(max_length=200)
    version = models.PositiveIntegerField(default=1)
    approved = models.BooleanField(default=False)
    components = models.JSONField(default=list)
    output_quantity = models.DecimalField(max_digits=20,decimal_places=6,default=Decimal('1'))
    class Meta: constraints=[models.UniqueConstraint(fields=['business','product','version'],name='bom_version_unique')]

class Asset(Owned):
    name = models.CharField(max_length=200)
    cost = models.DecimalField(max_digits=20,decimal_places=2)
    residual = models.DecimalField(max_digits=20,decimal_places=2,default=Decimal('0'))
    life_months = models.PositiveIntegerField()
    acquired = models.DateField()
    location = models.ForeignKey(Location,null=True,blank=True,on_delete=models.PROTECT)
    accounting = models.JSONField(default=dict,blank=True)

class TaxRule(Owned):
    name = models.CharField(max_length=150)
    rate = models.DecimalField(max_digits=10,decimal_places=6)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True,blank=True)
    account_code = models.CharField(max_length=40,default='TAX')
    def clean(self):
        super().clean()
        if self.rate is not None and (self.rate<0 or self.rate>100): raise ValidationError({'rate':'Use an approved percentage between 0 and 100.'})
        if self.effective_to and self.effective_from and self.effective_to<self.effective_from: raise ValidationError({'effective_to':'End date cannot precede the effective date.'})
        if self.business_id and not Account.objects.filter(business_id=self.business_id,code=self.account_code,category='liability').exists(): raise ValidationError({'account_code':'Select a configured liability account for this tax.'})

class AuditEvent(Owned):
    user = models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.PROTECT)
    action = models.CharField(max_length=80)
    target = models.CharField(max_length=120,blank=True)
    details = models.JSONField(default=dict)
    at = models.DateTimeField(auto_now_add=True)

class Attachment(Owned):
    document = models.ForeignKey(Document,on_delete=models.PROTECT)
    file = models.FileField(upload_to='private/%Y/%m/')
    filename = models.CharField(max_length=200)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

class LoginAttempt(models.Model):
    key = models.CharField(max_length=200,unique=True)
    failures = models.PositiveIntegerField(default=0)
    last_at = models.DateTimeField()

from .growth_models import (UserPreference, CollectionTask, CollectionNote, ReminderMessage, ReorderPolicy, PurchaseRequest,
 WorkCenter, WorkOrder, JobCard, WorkProduction, CutPlan, BinLocation, BlockPlacement, DeliveryConfirmation,
 InspectionTemplate, QualityInspection, MaterialLot, LotMovement, BudgetLine, ForecastItem, Equipment, MaintenanceJob,
 CustomerPrice, PortalGrant)
from .foreign_models import (ExchangeRate,ForeignExposure,ForeignMovement,ForeignWallet,ForeignWalletMovement,Remittance,RemittanceAdjustment,ForeignDeposit,ForeignDepositMovement)
from .cut_models import OrderCutDemand,OrderCutSheet
from .dispatch_models import (TransportVehicle,TransportDriver,DeliveryTrip,DeliveryLoad,DeliveryAcknowledgement,DeliveryDisputeResolution,CustomerQualityClaim,QualityClaimEvent,RecallCampaign,RecallBlockHold,RecallProductHold)
from .jobs_models import CostingProject,ProjectEstimate,ProjectDocument,ProjectBOMPlan,SubcontractJob,SubcontractEvent
from .commission_models import CommissionPolicy,CommissionEarning
from .late_cost_models import LateCostBill,LateCostAllocation
from .excellence_models import ClosingCycle,ClosingReview,PortalListing,PortalSubmission,PortalReview,MessageEvent,CustomerNotice
from .procurement_models import SupplierClaim,SupplierClaimResolution,CycleCountSession,WeighingDevice,ScaleCalibration,WeightMeasurement
from .cashier_models import CashDrawer,CashShift,CashShiftEntry,CashShiftCount,CashHandover
from .statement_models import StatementImport,StatementRow,StatementReview,StatementMatch,StatementReconciliation
from .sourcing_models import SourcingRequest,SupplierOffer,SourcingAward
from .crm_models import CRMOpportunity,CRMEvent,CRMActivity
from .workspace_models import WorkspacePreference,GuideProgress
from .capture_models import DocumentCapture,CaptureReview

from .money_models import MoneyInstrument,MoneyInstrumentEntry
from .tax_models import TaxSchedule,TaxScheduleChange
