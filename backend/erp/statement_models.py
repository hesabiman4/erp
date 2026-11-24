"""Immutable external statement evidence; matches reference the existing ledger."""
from django.db import models
from django.db.models import Q
from .models import Owned


class StatementImport(Owned):
    instrument=models.ForeignKey('erp.MoneyInstrument',null=True,blank=True,on_delete=models.PROTECT)
    location = models.ForeignKey('erp.Location', on_delete=models.PROTECT)
    source_type = models.CharField(max_length=8)
    institution = models.CharField(max_length=150)
    account_reference = models.CharField(max_length=100)
    account = models.ForeignKey('erp.Account', null=True, blank=True, on_delete=models.PROTECT)
    currency = models.CharField(max_length=3, default='AFN')
    starts = models.DateField()
    ends = models.DateField()
    opening_balance = models.DecimalField(max_digits=20, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=20, decimal_places=2)
    filename = models.CharField(max_length=200)
    sha256 = models.CharField(max_length=64)
    original = models.BinaryField()
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['business','location','source_type','account_reference','sha256'],name='statement_file_once'), models.CheckConstraint(condition=Q(starts__lte=models.F('ends')),name='statement_date_window')]


class StatementRow(Owned):
    statement = models.ForeignKey(StatementImport, on_delete=models.PROTECT, related_name='rows')
    position = models.PositiveIntegerField()
    date = models.DateField()
    reference = models.CharField(max_length=150, blank=True)
    description = models.CharField(max_length=1000)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    fingerprint = models.CharField(max_length=64)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['statement','position'],name='statement_position_once'), models.UniqueConstraint(fields=['business','fingerprint'],name='statement_row_once'),models.CheckConstraint(condition=~Q(amount=0),name='statement_row_nonzero')]


class StatementReview(Owned):
    row = models.ForeignKey(StatementRow, on_delete=models.PROTECT, related_name='reviews')
    outcome = models.CharField(max_length=12)
    entry = models.ForeignKey('erp.Entry', null=True, blank=True, on_delete=models.PROTECT)
    note = models.TextField()
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)


class StatementMatch(Owned):
    row = models.ForeignKey(StatementRow, on_delete=models.PROTECT, related_name='matches')
    entry = models.ForeignKey('erp.Entry', on_delete=models.PROTECT)
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
    released_by = models.OneToOneField('erp.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    class Meta:
        constraints = [models.UniqueConstraint(fields=['business','entry'],condition=Q(released_by__isnull=True),name='statement_entry_active_once'),models.UniqueConstraint(fields=['row'],condition=Q(released_by__isnull=True),name='statement_row_active_once')]


class StatementReconciliation(Owned):
    statement = models.OneToOneField(StatementImport, on_delete=models.PROTECT, related_name='reconciliation')
    bank_document = models.OneToOneField('erp.Document', on_delete=models.PROTECT, related_name='+')
    source = models.OneToOneField('erp.Document', on_delete=models.PROTECT)
