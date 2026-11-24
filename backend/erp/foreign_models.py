"""Foreign monetary subledgers; Entry always records functional AFN values."""
from django.db import models
from django.db.models import Q
from .models import Owned

CURRENCIES=[('USD','US dollar'),('PKR','Pakistani rupee')]
class ExchangeRate(Owned):
    currency=models.CharField(max_length=3,choices=CURRENCIES)
    date=models.DateField()
    rate=models.DecimalField(max_digits=24,decimal_places=8)
    source=models.OneToOneField('erp.Document',on_delete=models.PROTECT)
    reference=models.CharField(max_length=250)
    class Meta:constraints=[models.CheckConstraint(condition=Q(rate__gt=0),name='fx_rate_positive')]

class ForeignExposure(Owned):
    invoice=models.OneToOneField('erp.Document',on_delete=models.PROTECT,related_name='foreign_exposure')
    currency=models.CharField(max_length=3,choices=CURRENCIES)
    foreign_amount=models.DecimalField(max_digits=20,decimal_places=2)
    initial_rate=models.DecimalField(max_digits=24,decimal_places=8)
    source=models.OneToOneField('erp.Document',on_delete=models.PROTECT,related_name='+')
    class Meta:constraints=[models.CheckConstraint(condition=Q(foreign_amount__gt=0,initial_rate__gt=0),name='fx_exposure_positive')]

class ForeignMovement(Owned):
    exposure=models.ForeignKey(ForeignExposure,on_delete=models.PROTECT,related_name='movements')
    document=models.ForeignKey('erp.Document',on_delete=models.PROTECT)
    quantity=models.DecimalField(max_digits=20,decimal_places=2,default=0)
    base_value=models.DecimalField(max_digits=20,decimal_places=2)
    kind=models.CharField(max_length=16)

class ForeignWallet(Owned):
    name=models.CharField(max_length=150)
    location=models.ForeignKey('erp.Location',on_delete=models.PROTECT)
    currency=models.CharField(max_length=3,choices=CURRENCIES)
    kind=models.CharField(max_length=8,choices=[('cash','Cash'),('bank','Bank')])
    source=models.OneToOneField('erp.Document',on_delete=models.PROTECT)
    class Meta:constraints=[models.UniqueConstraint(fields=['business','name'],name='fx_wallet_name_scope')]

class ForeignWalletMovement(Owned):
    wallet=models.ForeignKey(ForeignWallet,on_delete=models.PROTECT,related_name='movements')
    document=models.ForeignKey('erp.Document',on_delete=models.PROTECT)
    quantity=models.DecimalField(max_digits=20,decimal_places=2)
    base_value=models.DecimalField(max_digits=20,decimal_places=2)

class Remittance(Owned):
    source_wallet=models.ForeignKey(ForeignWallet,on_delete=models.PROTECT,related_name='+')
    destination_wallet=models.ForeignKey(ForeignWallet,on_delete=models.PROTECT,related_name='+')
    foreign_amount=models.DecimalField(max_digits=20,decimal_places=2)
    carrying_amount=models.DecimalField(max_digits=20,decimal_places=2)
    reference=models.CharField(max_length=250)
    source=models.OneToOneField('erp.Document',on_delete=models.PROTECT)
    completed_by=models.OneToOneField('erp.Document',on_delete=models.PROTECT,null=True,blank=True,related_name='+')
    class Meta:constraints=[models.CheckConstraint(condition=Q(foreign_amount__gt=0,carrying_amount__gt=0),name='fx_remit_positive')]

class RemittanceAdjustment(Owned):
    remittance=models.ForeignKey(Remittance,on_delete=models.PROTECT,related_name='adjustments')
    document=models.ForeignKey('erp.Document',on_delete=models.PROTECT)
    base_value=models.DecimalField(max_digits=20,decimal_places=2)

class ForeignDeposit(Owned):
    """Refundable monetary credit, never a nonmonetary goods advance."""
    party=models.ForeignKey('erp.Party',on_delete=models.PROTECT)
    location=models.ForeignKey('erp.Location',on_delete=models.PROTECT)
    currency=models.CharField(max_length=3,choices=CURRENCIES)
    side=models.CharField(max_length=8,choices=[('customer','Customer liability'),('supplier','Supplier asset')])
    foreign_amount=models.DecimalField(max_digits=20,decimal_places=2)
    base_value=models.DecimalField(max_digits=20,decimal_places=2)
    source=models.OneToOneField('erp.Document',on_delete=models.PROTECT,related_name='foreign_deposit')
    class Meta:constraints=[models.CheckConstraint(condition=Q(foreign_amount__gt=0,base_value__gte=0),name='fx_deposit_positive')]

class ForeignDepositMovement(Owned):
    deposit=models.ForeignKey(ForeignDeposit,on_delete=models.PROTECT,related_name='movements')
    document=models.ForeignKey('erp.Document',on_delete=models.PROTECT)
    quantity=models.DecimalField(max_digits=20,decimal_places=2,default=0)
    base_value=models.DecimalField(max_digits=20,decimal_places=2)
    kind=models.CharField(max_length=16)
