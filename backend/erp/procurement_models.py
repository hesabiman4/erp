"""Reviewed supplier cases, blind counting assignments and measured weights."""
from django.db import models
from django.db.models import Q, F
from .models import Owned


class SupplierClaim(Owned):
    supplier = models.ForeignKey('erp.Party', on_delete=models.PROTECT)
    document = models.ForeignKey('erp.Document', on_delete=models.PROTECT, related_name='supplier_claims')
    line_index = models.PositiveIntegerField()
    product = models.ForeignKey('erp.Product', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=24, decimal_places=6)
    reason = models.CharField(max_length=24)
    description = models.TextField()
    state = models.CharField(max_length=16, default='open')
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name='supplier_claim_quantity_positive')]


class SupplierClaimResolution(Owned):
    claim = models.OneToOneField(SupplierClaim, on_delete=models.PROTECT, related_name='resolution')
    outcome = models.CharField(max_length=24)
    financial_document = models.OneToOneField('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='supplier_claim_resolution')
    note = models.TextField()
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)


class CycleCountSession(Owned):
    warehouse = models.ForeignKey('erp.Warehouse', on_delete=models.PROTECT)
    assignee = models.ForeignKey('erp.Membership', on_delete=models.PROTECT)
    due_date = models.DateField()
    targets = models.JSONField(default=list)
    instructions = models.TextField(blank=True)
    state = models.CharField(max_length=16, default='assigned')
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    observation = models.OneToOneField('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='cycle_count_observation')
    adjustment = models.OneToOneField('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='cycle_count_adjustment')
    reviewed_by = models.OneToOneField('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')


class WeighingDevice(Owned):
    warehouse = models.ForeignKey('erp.Warehouse', on_delete=models.PROTECT)
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=150)
    capacity_kg = models.DecimalField(max_digits=24, decimal_places=6)
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['business', 'code'], name='weighing_device_code_business'), models.CheckConstraint(condition=Q(capacity_kg__gt=0), name='weighing_capacity_positive')]


class ScaleCalibration(Owned):
    device = models.ForeignKey(WeighingDevice, on_delete=models.PROTECT, related_name='calibrations')
    next_due = models.DateField()
    reference = models.CharField(max_length=200)
    note = models.TextField()
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)


class WeightMeasurement(Owned):
    device = models.ForeignKey(WeighingDevice, on_delete=models.PROTECT)
    calibration = models.ForeignKey(ScaleCalibration, on_delete=models.PROTECT)
    product = models.ForeignKey('erp.Product', on_delete=models.PROTECT)
    gross_kg = models.DecimalField(max_digits=24, decimal_places=6)
    tare_kg = models.DecimalField(max_digits=24, decimal_places=6)
    net_kg = models.DecimalField(max_digits=24, decimal_places=6)
    container_count = models.PositiveIntegerField(default=1)
    note = models.TextField(blank=True)
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(gross_kg__gt=0, tare_kg__gte=0, net_kg__gt=0, container_count__gt=0), name='measured_weight_positive'), models.CheckConstraint(condition=Q(net_kg=F('gross_kg')-F('tare_kg')), name='measured_net_equals_gross_minus_tare')]
