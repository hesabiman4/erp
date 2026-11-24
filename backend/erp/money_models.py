"""Actual AFN instruments below the existing CASH/BANK control accounts."""
from django.db import models
from django.db.models import Q,F
from django.db.models.functions import Lower
from .models import Owned


class MoneyInstrument(Owned):
    location=models.ForeignKey('erp.Location',on_delete=models.PROTECT)
    kind=models.CharField(max_length=4,choices=[('CASH','Cash'),('BANK','Bank')])
    code=models.CharField(max_length=40)
    name=models.CharField(max_length=150)
    institution=models.CharField(max_length=150,blank=True)
    account_reference=models.CharField(max_length=100,blank=True)
    legacy=models.BooleanField(default=False)
    active=models.BooleanField(default=True)
    source=models.OneToOneField('erp.Document',null=True,blank=True,on_delete=models.PROTECT,related_name='+')
    class Meta:
        constraints=[models.UniqueConstraint(fields=['business','code'],name='money_instrument_code'),
            models.UniqueConstraint(fields=['business','location','kind'],condition=Q(legacy=True),name='one_legacy_money_pool'),
            models.CheckConstraint(condition=Q(kind__in=['CASH','BANK']),name='money_instrument_kind'),
            models.UniqueConstraint(Lower('institution'),Lower('account_reference'),F('business'),F('location'),condition=Q(kind='BANK')&~Q(institution=''),name='unique_bank_instrument_identity')]


class MoneyInstrumentEntry(Owned):
    instrument=models.ForeignKey(MoneyInstrument,on_delete=models.PROTECT,related_name='entry_links')
    entry=models.OneToOneField('erp.Entry',on_delete=models.PROTECT,related_name='money_link')
