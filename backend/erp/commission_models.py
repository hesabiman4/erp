from django.db import models
from django.db.models import Q
from .models import Owned

class CommissionPolicy(Owned):
    employee=models.ForeignKey('erp.Employee',on_delete=models.PROTECT)
    rate=models.DecimalField(max_digits=9,decimal_places=6)
    effective_from=models.DateField()
    effective_to=models.DateField(null=True,blank=True)
    source=models.OneToOneField('erp.Document',on_delete=models.PROTECT)
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(rate__gt=0,rate__lte=100),name='commission_rate_percentage')]

class CommissionEarning(Owned):
    policy=models.ForeignKey(CommissionPolicy,on_delete=models.PROTECT)
    invoice=models.ForeignKey('erp.Document',on_delete=models.PROTECT,related_name='commission_earnings')
    eligible_amount=models.DecimalField(max_digits=20,decimal_places=2)
    amount=models.DecimalField(max_digits=20,decimal_places=2)
    source=models.OneToOneField('erp.Document',on_delete=models.PROTECT,related_name='commission_earning')
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(amount__gt=0,eligible_amount__gt=0),name='commission_earning_positive')]
