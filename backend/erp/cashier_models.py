"""Physical custody over the existing location CASH account, not another GL."""
from django.db import models
from django.db.models import Q
from .models import Owned


class CashDrawer(Owned):
    location = models.ForeignKey('erp.Location',on_delete=models.PROTECT)
    instrument = models.OneToOneField('erp.MoneyInstrument',null=True,blank=True,on_delete=models.PROTECT)
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=150)
    source = models.OneToOneField('erp.Document',on_delete=models.PROTECT)
    activated_by = models.OneToOneField('erp.Document',null=True,blank=True,on_delete=models.PROTECT,related_name='+')
    class Meta:
        constraints=[models.UniqueConstraint(fields=['business','code'],name='cash_drawer_code_business')]


class CashShift(Owned):
    drawer = models.ForeignKey(CashDrawer,on_delete=models.PROTECT,related_name='shifts')
    cashier = models.ForeignKey('erp.Membership',on_delete=models.PROTECT)
    opening_amount = models.DecimalField(max_digits=20,decimal_places=2)
    opening_denominations = models.JSONField(default=list)
    state = models.CharField(max_length=16,default='open')
    source = models.OneToOneField('erp.Document',on_delete=models.PROTECT)
    reviewed_by = models.OneToOneField('erp.Document',null=True,blank=True,on_delete=models.PROTECT,related_name='+')
    class Meta:
        constraints=[models.UniqueConstraint(fields=['drawer'],condition=Q(state__in=['open','counted']),name='one_active_cash_shift'),models.CheckConstraint(condition=Q(opening_amount__gte=0),name='cash_shift_opening_nonnegative')]


class CashShiftEntry(Owned):
    shift = models.ForeignKey(CashShift,on_delete=models.PROTECT,related_name='cash_entries')
    entry = models.OneToOneField('erp.Entry',on_delete=models.PROTECT)
    reason = models.CharField(max_length=1000,blank=True)


class CashShiftCount(Owned):
    shift = models.ForeignKey(CashShift,on_delete=models.PROTECT,related_name='counts')
    denominations = models.JSONField(default=list)
    expected = models.DecimalField(max_digits=20,decimal_places=2)
    counted = models.DecimalField(max_digits=20,decimal_places=2)
    variance = models.DecimalField(max_digits=20,decimal_places=2)
    note = models.TextField()
    source = models.OneToOneField('erp.Document',on_delete=models.PROTECT)


class CashHandover(Owned):
    shift = models.OneToOneField(CashShift,on_delete=models.PROTECT)
    receiver = models.ForeignKey('erp.Membership',on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=20,decimal_places=2)
    note = models.TextField()
    source = models.OneToOneField('erp.Document',on_delete=models.PROTECT)
    accepted_by = models.OneToOneField('erp.Document',null=True,blank=True,on_delete=models.PROTECT,related_name='+')
