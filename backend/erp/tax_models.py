"""Immutable tax schedule revisions; legacy flat TaxRule stays compatible."""
from django.conf import settings
from django.db import models
from .models import Owned


class TaxSchedule(Owned):
    TAX_TYPES = [('salary_wht','مالیه معاش'),('brt','مالیه عواید ناخالص'),('cit','مالیه بر عایدات'),
                 ('rent_wht','مالیه کرایه'),('contractor_wht','مالیه قراردادی'),('vat','مالیه ارزش افزوده'),
                 ('import_income_advance','پیش‌پرداخت مالیه عایدات در گمرک'),('import_brt_advance','پیش‌پرداخت مالیه عواید ناخالص در گمرک')]
    name_fa = models.CharField(max_length=180)
    name_en = models.CharField(max_length=180,blank=True)
    name_ps = models.CharField(max_length=180,blank=True)
    tax_type = models.CharField(max_length=32,choices=TAX_TYPES)
    sector = models.CharField(max_length=80,default='general')
    schedule_version = models.CharField(max_length=64)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True,blank=True)
    currency_code = models.CharField(max_length=3,default='AFN')
    basis = models.CharField(max_length=32)
    rate = models.DecimalField(max_digits=9,decimal_places=6,null=True,blank=True)
    brackets = models.JSONField(default=list,blank=True)
    rounding_places = models.PositiveSmallIntegerField(default=2)
    source_url = models.URLField(max_length=1000)
    source_retrieved_on = models.DateField()
    notes = models.TextField(blank=True)
    supersedes = models.ForeignKey('self',null=True,blank=True,on_delete=models.PROTECT)
    requires_confirmation = models.BooleanField(default=True)
    verified_at = models.DateTimeField(null=True,blank=True)
    confirmation_revision = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['business','tax_type','sector','schedule_version'],name='tax_schedule_version_business'),
                       models.CheckConstraint(condition=models.Q(rounding_places__lte=6),name='tax_schedule_rounding_places'),
                       models.CheckConstraint(condition=models.Q(rate__isnull=True)|models.Q(rate__gte=0,rate__lte=100),name='tax_schedule_rate_range'),
                       models.CheckConstraint(condition=models.Q(requires_confirmation=True,verified_at__isnull=True)|models.Q(requires_confirmation=False,verified_at__isnull=False),name='tax_schedule_confirmation_state'),
                       models.CheckConstraint(condition=models.Q(effective_to__isnull=True)|models.Q(effective_to__gte=models.F('effective_from')),name='tax_schedule_date_order')]


class TaxScheduleChange(Owned):
    schedule = models.ForeignKey(TaxSchedule,on_delete=models.PROTECT,related_name='changes')
    operation = models.CharField(max_length=12,choices=[('create','ایجاد نسخه'),('confirm','تأیید نسخه'),('revoke','لغو تأیید')])
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    reason = models.TextField()
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    request_key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['business','request_key'],name='tax_schedule_change_idempotency')]
