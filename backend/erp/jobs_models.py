"""Project/job records separate estimates and associations from accounting ledgers."""
from django.db import models
from django.db.models import Q
from .models import Owned


class CostingProject(Owned):
    location = models.ForeignKey('erp.Location', on_delete=models.PROTECT)
    customer = models.ForeignKey('erp.Party', on_delete=models.PROTECT)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    state = models.CharField(max_length=16, default='open')
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    closed_by = models.OneToOneField('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    class Meta:
        constraints = [models.UniqueConstraint(fields=['business', 'code'], name='costing_project_code_business')]


class ProjectEstimate(Owned):
    project = models.ForeignKey(CostingProject, on_delete=models.PROTECT, related_name='estimates')
    lines = models.JSONField(default=list)
    estimated_cost = models.DecimalField(max_digits=20, decimal_places=2)
    estimated_revenue = models.DecimalField(max_digits=20, decimal_places=2)
    note = models.TextField(blank=True)
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)


class ProjectDocument(Owned):
    project = models.ForeignKey(CostingProject, on_delete=models.PROTECT, related_name='document_links')
    document = models.OneToOneField('erp.Document', on_delete=models.PROTECT, related_name='costing_project_link')
    note = models.TextField(blank=True)
    source = models.ForeignKey('erp.Document', on_delete=models.PROTECT, related_name='+')


class ProjectBOMPlan(Owned):
    project = models.ForeignKey(CostingProject, on_delete=models.PROTECT, related_name='bom_plans')
    bom = models.ForeignKey('erp.BOM', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=24, decimal_places=6)
    snapshot = models.JSONField(default=dict)
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)


class SubcontractJob(Owned):
    project = models.ForeignKey(CostingProject, on_delete=models.PROTECT, related_name='subcontracts')
    supplier = models.ForeignKey('erp.Party', on_delete=models.PROTECT)
    warehouse = models.ForeignKey('erp.Warehouse', on_delete=models.PROTECT)
    product = models.ForeignKey('erp.Product', on_delete=models.PROTECT)
    planned_quantity = models.DecimalField(max_digits=24, decimal_places=6)
    instructions = models.TextField()
    state = models.CharField(max_length=20, default='open')
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    closed_by = models.OneToOneField('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(planned_quantity__gt=0), name='subcontract_plan_positive')]


class SubcontractEvent(Owned):
    subcontract = models.ForeignKey(SubcontractJob, on_delete=models.PROTECT, related_name='events')
    kind = models.CharField(max_length=20)
    document = models.OneToOneField('erp.Document', on_delete=models.PROTECT, related_name='subcontract_event')
    processing_bill = models.ForeignKey('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    quantity = models.DecimalField(max_digits=24, decimal_places=6, default=0)
    note = models.TextField(blank=True)
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT, related_name='+')
