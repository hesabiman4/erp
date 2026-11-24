"""Supplier offers are procurement evidence, not received inventory or bills."""
from django.db import models
from django.db.models import Q
from .models import Owned


class SourcingRequest(Owned):
    warehouse = models.ForeignKey('erp.Warehouse', on_delete=models.PROTECT)
    desired_date = models.DateField()
    lines = models.JSONField(default=list)
    note = models.TextField(blank=True)
    state = models.CharField(max_length=16, default='open')
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    closed_by = models.OneToOneField('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')


class SupplierOffer(Owned):
    request = models.ForeignKey(SourcingRequest, on_delete=models.PROTECT, related_name='offers')
    supplier = models.ForeignKey('erp.Party', on_delete=models.PROTECT)
    reference = models.CharField(max_length=150)
    valid_through = models.DateField()
    lead_days = models.PositiveSmallIntegerField()
    payment_terms = models.CharField(max_length=250)
    lines = models.JSONField(default=list)
    freight_estimate = models.DecimalField(max_digits=20, decimal_places=2)
    merchandise_total = models.DecimalField(max_digits=20, decimal_places=2)
    comparison_total = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=3, default='AFN')
    note = models.TextField(blank=True)
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['business','request','supplier','reference'],name='supplier_offer_reference_scope'),
            models.CheckConstraint(condition=Q(freight_estimate__gte=0,merchandise_total__gte=0,comparison_total__gte=0),name='supplier_offer_amounts_nonnegative'),
        ]


class SourcingAward(Owned):
    request = models.OneToOneField(SourcingRequest, on_delete=models.PROTECT, related_name='award')
    offer = models.OneToOneField(SupplierOffer, on_delete=models.PROTECT, related_name='award')
    purchase_order = models.OneToOneField('erp.Document', on_delete=models.PROTECT, related_name='sourcing_award')
    reason = models.TextField()
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
