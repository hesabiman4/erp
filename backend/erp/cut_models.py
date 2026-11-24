"""Persistent commercial demand and individual held-sheet provenance."""
from django.db import models
from django.db.models import Q
from .models import Owned


class OrderCutDemand(Owned):
    plan=models.ForeignKey('erp.CutPlan',on_delete=models.PROTECT,related_name='order_demands')
    order=models.ForeignKey('erp.Document',on_delete=models.PROTECT,related_name='cut_demands')
    order_index=models.PositiveIntegerField()
    thickness_mm=models.DecimalField(max_digits=18,decimal_places=3)
    sheet_count=models.PositiveIntegerField()
    quantity_cm=models.DecimalField(max_digits=24,decimal_places=6)
    state=models.CharField(max_length=12,default='planned',choices=[('planned','Planned'),('cut','Cut'),('cancelled','Cancelled')])
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(thickness_mm__gt=0,sheet_count__gt=0,quantity_cm__gt=0),name='order_cut_demand_positive')]
        indexes=[models.Index(fields=['business','order','order_index','state'],name='order_cut_demand_scope')]


class OrderCutSheet(Owned):
    demand=models.ForeignKey(OrderCutDemand,on_delete=models.PROTECT,related_name='sheets')
    block=models.OneToOneField('erp.Block',on_delete=models.PROTECT,related_name='order_cut_sheet')
    quantity_cm=models.DecimalField(max_digits=24,decimal_places=6)
    fulfilled_document=models.ForeignKey('erp.Document',null=True,blank=True,on_delete=models.PROTECT,related_name='fulfilled_cut_sheets')
    released_by=models.ForeignKey('erp.Document',null=True,blank=True,on_delete=models.PROTECT,related_name='released_cut_sheets')
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(quantity_cm__gt=0),name='order_cut_sheet_positive'),models.CheckConstraint(condition=Q(fulfilled_document__isnull=True)|Q(released_by__isnull=True),name='order_cut_sheet_one_disposition')]
