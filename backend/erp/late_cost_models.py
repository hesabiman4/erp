from django.db import models
from django.db.models import Q
from .models import Owned


class LateCostBill(Owned):
    supplier = models.ForeignKey('erp.Party', on_delete=models.PROTECT)
    reference = models.CharField(max_length=100)
    invoice = models.OneToOneField('erp.Document', on_delete=models.PROTECT, related_name='late_cost_bill')
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    receipts = models.JSONField(default=list)
    reason = models.TextField()
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT, related_name='+')
    class Meta:
        constraints = [models.UniqueConstraint(fields=['business', 'supplier', 'reference'], name='late_cost_supplier_reference'), models.CheckConstraint(condition=Q(amount__gt=0), name='late_cost_bill_positive')]


class LateCostAllocation(Owned):
    bill = models.ForeignKey(LateCostBill, on_delete=models.PROTECT, related_name='allocations')
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    lines = models.JSONField(default=list)
    basis = models.TextField()
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='late_cost_allocation_positive')]
