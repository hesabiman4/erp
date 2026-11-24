"""Transport and quality-case records; stock/GL authority remains in core ledgers."""
from django.db import models
from django.db.models import Q
from .models import Owned


class TransportVehicle(Owned):
    location = models.ForeignKey('erp.Location', on_delete=models.PROTECT)
    plate = models.CharField(max_length=50)
    description = models.CharField(max_length=200, blank=True)
    capacity_note = models.CharField(max_length=150, blank=True)
    active = models.BooleanField(default=True)
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['business', 'plate'], name='transport_vehicle_plate_business')]


class TransportDriver(Owned):
    location = models.ForeignKey('erp.Location', on_delete=models.PROTECT)
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=50, blank=True)
    active = models.BooleanField(default=True)
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)


class DeliveryTrip(Owned):
    warehouse = models.ForeignKey('erp.Warehouse', on_delete=models.PROTECT)
    vehicle = models.ForeignKey(TransportVehicle, on_delete=models.PROTECT)
    driver = models.ForeignKey(TransportDriver, on_delete=models.PROTECT)
    scheduled_date = models.DateField()
    destination = models.CharField(max_length=250)
    notes = models.TextField(blank=True)
    state = models.CharField(max_length=20, default='planned')
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    dispatched_by = models.OneToOneField('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    closed_by = models.OneToOneField('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    class Meta:
        indexes = [models.Index(fields=['business', 'state', 'scheduled_date'], name='delivery_trip_state_date')]


class DeliveryLoad(Owned):
    trip = models.ForeignKey(DeliveryTrip, on_delete=models.PROTECT, related_name='loads')
    document = models.ForeignKey('erp.Document', on_delete=models.PROTECT, related_name='transport_loads')
    line_index = models.PositiveIntegerField()
    product = models.ForeignKey('erp.Product', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=24, decimal_places=6)
    source = models.ForeignKey('erp.Document', on_delete=models.PROTECT, related_name='+')
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name='delivery_load_positive')]
        indexes = [models.Index(fields=['business', 'document', 'line_index'], name='delivery_source_line')]


class DeliveryAcknowledgement(Owned):
    load = models.ForeignKey(DeliveryLoad, on_delete=models.PROTECT, related_name='acknowledgements')
    accepted = models.DecimalField(max_digits=24, decimal_places=6, default=0)
    disputed = models.DecimalField(max_digits=24, decimal_places=6, default=0)
    recipient = models.CharField(max_length=200)
    note = models.TextField(blank=True)
    attachments = models.JSONField(default=list, blank=True)
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(accepted__gte=0, disputed__gte=0) & (Q(accepted__gt=0) | Q(disputed__gt=0)), name='delivery_ack_quantities')]


class DeliveryDisputeResolution(Owned):
    acknowledgement = models.OneToOneField(DeliveryAcknowledgement, on_delete=models.PROTECT, related_name='resolution')
    outcome = models.CharField(max_length=30)
    note = models.TextField()
    financial_document = models.ForeignKey('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)


class CustomerQualityClaim(Owned):
    invoice = models.ForeignKey('erp.Document', on_delete=models.PROTECT, related_name='quality_claims')
    line_index = models.PositiveIntegerField()
    product = models.ForeignKey('erp.Product', on_delete=models.PROTECT)
    block = models.ForeignKey('erp.Block', null=True, blank=True, on_delete=models.PROTECT)
    batch = models.ForeignKey('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    quantity = models.DecimalField(max_digits=24, decimal_places=6)
    reason = models.CharField(max_length=30)
    description = models.TextField()
    state = models.CharField(max_length=20, default='open')
    disposition = models.CharField(max_length=20, blank=True)
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    class Meta:
        indexes = [models.Index(fields=['business', 'state'], name='customer_claim_state')]
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name='customer_claim_quantity')]


class QualityClaimEvent(Owned):
    claim = models.ForeignKey(CustomerQualityClaim, on_delete=models.PROTECT, related_name='events')
    kind = models.CharField(max_length=20)
    note = models.TextField()
    inspection = models.ForeignKey('erp.QualityInspection', null=True, blank=True, on_delete=models.PROTECT)
    financial_document = models.ForeignKey('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    replacement = models.ForeignKey('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    attachments = models.JSONField(default=list, blank=True)
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)


class RecallCampaign(Owned):
    lot = models.ForeignKey('erp.MaterialLot', null=True, blank=True, on_delete=models.PROTECT)
    batch = models.ForeignKey('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    reason = models.TextField()
    state = models.CharField(max_length=16, default='open')
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    closed_by = models.OneToOneField('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    class Meta:
        constraints = [models.CheckConstraint(condition=(Q(lot__isnull=False, batch__isnull=True) | Q(lot__isnull=True, batch__isnull=False)), name='recall_exactly_one_basis')]


class RecallBlockHold(Owned):
    campaign = models.ForeignKey(RecallCampaign, on_delete=models.PROTECT, related_name='block_holds')
    block = models.ForeignKey('erp.Block', on_delete=models.PROTECT)
    prior_status = models.CharField(max_length=20)
    source = models.ForeignKey('erp.Document', on_delete=models.PROTECT, related_name='+')
    released_by = models.ForeignKey('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    class Meta:
        constraints = [models.UniqueConstraint(fields=['campaign', 'block'], name='recall_campaign_block')]


class RecallProductHold(Owned):
    campaign = models.ForeignKey(RecallCampaign, on_delete=models.PROTECT, related_name='product_holds')
    product = models.ForeignKey('erp.Product', on_delete=models.PROTECT)
    source = models.ForeignKey('erp.Document', on_delete=models.PROTECT, related_name='+')
    released_by = models.ForeignKey('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    class Meta:
        constraints = [models.UniqueConstraint(fields=['campaign', 'product'], name='recall_campaign_product')]
