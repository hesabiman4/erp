"""Commercial follow-up evidence; no opportunity is a sale or receivable."""
from django.db import models
from .models import Owned


class CRMOpportunity(Owned):
    title = models.CharField(max_length=180)
    location = models.ForeignKey('erp.Location', on_delete=models.PROTECT)
    product_lines = models.JSONField(default=list)
    assigned = models.ForeignKey('erp.Membership', on_delete=models.PROTECT)
    party = models.ForeignKey('erp.Party', null=True, blank=True, on_delete=models.PROTECT)
    prospect_name = models.CharField(max_length=180)
    phone = models.CharField(max_length=80, blank=True)
    expected_amount = models.DecimalField(max_digits=20, decimal_places=2)
    expected_date = models.DateField()
    note = models.TextField(blank=True)
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)


class CRMEvent(Owned):
    opportunity = models.ForeignKey(CRMOpportunity, on_delete=models.PROTECT, related_name='events')
    kind = models.CharField(max_length=20)
    stage = models.CharField(max_length=20, blank=True)
    assigned = models.ForeignKey('erp.Membership', null=True, blank=True, on_delete=models.PROTECT)
    quotation = models.OneToOneField('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='crm_link')
    reason = models.TextField(blank=True)
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    class Meta: ordering = ['id']


class CRMActivity(Owned):
    opportunity = models.ForeignKey(CRMOpportunity, on_delete=models.PROTECT, related_name='activities')
    assigned = models.ForeignKey('erp.Membership', on_delete=models.PROTECT)
    due_date = models.DateField()
    task = models.CharField(max_length=500)
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    completed_by = models.OneToOneField('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
