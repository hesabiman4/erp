"""Reviewed operational records; no alternative stock or financial ledger."""
from django.conf import settings
from django.db import models
from .models import Owned


class ClosingCycle(Owned):
    starts = models.DateField()
    ends = models.DateField()
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['business', 'ends'], name='closing_end_business')]


class ClosingReview(Owned):
    cycle = models.ForeignKey(ClosingCycle, on_delete=models.PROTECT, related_name='reviews')
    task = models.CharField(max_length=24)
    assignee = models.ForeignKey('erp.Membership', on_delete=models.PROTECT)
    evidence = models.ForeignKey('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    note = models.TextField()
    accepted = models.BooleanField(default=False)
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)


class PortalListing(Owned):
    grant = models.ForeignKey('erp.PortalGrant', on_delete=models.PROTECT)
    product = models.ForeignKey('erp.Product', on_delete=models.PROTECT)
    profile = models.CharField(max_length=100, blank=True)
    active = models.BooleanField(default=True)
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['business','grant','product','profile'],name='portal_listing_scope')]


class PortalSubmission(Owned):
    grant = models.ForeignKey('erp.PortalGrant', on_delete=models.PROTECT)
    kind = models.CharField(max_length=16)
    payload = models.JSONField(default=dict)
    invoice = models.ForeignKey('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    key = models.CharField(max_length=100)
    digest = models.CharField(max_length=64)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['business','grant','key'],name='portal_submission_idempotent')]


class PortalReview(Owned):
    submission = models.OneToOneField(PortalSubmission, on_delete=models.PROTECT, related_name='review')
    outcome = models.CharField(max_length=16)
    reason = models.TextField()
    commercial_document = models.ForeignKey('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)


class MessageEvent(Owned):
    message = models.ForeignKey('erp.ReminderMessage', on_delete=models.PROTECT, related_name='events')
    state = models.CharField(max_length=16)
    provider_reference = models.CharField(max_length=150, blank=True)
    evidence = models.TextField()
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)


class CustomerNotice(Owned):
    document = models.ForeignKey('erp.Document', on_delete=models.PROTECT, related_name='+')
    party = models.ForeignKey('erp.Party', on_delete=models.PROTECT)
    channel = models.CharField(max_length=12)
    recipient = models.CharField(max_length=50)
    language = models.CharField(max_length=8, default='fa-AF')
    template = models.CharField(max_length=24)
    body = models.TextField()
    authorized_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    state = models.CharField(max_length=16, default='queued')
    attempts = models.PositiveIntegerField(default=0)
    provider_reference = models.CharField(max_length=150, blank=True)
    last_error = models.CharField(max_length=250, blank=True)
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
