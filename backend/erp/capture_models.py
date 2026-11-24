"""Private original documents and append-only reviewed draft provenance."""
from django.db import models
from .models import Owned


class DocumentCapture(Owned):
    location=models.ForeignKey('erp.Location',on_delete=models.PROTECT)
    filename=models.CharField(max_length=200)
    media_type=models.CharField(max_length=40)
    sha256=models.CharField(max_length=64)
    original=models.BinaryField()
    preview=models.BinaryField()
    extracted_text=models.TextField()
    suggestions=models.JSONField(default=dict)
    extraction=models.JSONField(default=dict)
    source=models.OneToOneField('erp.Document',on_delete=models.PROTECT)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['business','sha256'],name='capture_original_once')]


class CaptureReview(Owned):
    capture=models.OneToOneField(DocumentCapture,on_delete=models.PROTECT,related_name='review')
    outcome=models.CharField(max_length=12)
    reason=models.TextField()
    approved_data=models.JSONField(default=dict)
    supplier=models.ForeignKey('erp.Party',null=True,blank=True,on_delete=models.PROTECT)
    supplier_reference=models.CharField(max_length=150,blank=True)
    draft=models.OneToOneField('erp.Document',null=True,blank=True,on_delete=models.PROTECT,related_name='+')
    posted_document=models.OneToOneField('erp.Document',null=True,blank=True,on_delete=models.PROTECT,related_name='+')
    source=models.OneToOneField('erp.Document',on_delete=models.PROTECT)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['business','supplier','supplier_reference'],condition=models.Q(supplier__isnull=False)&~models.Q(supplier_reference=''),name='capture_supplier_reference_once')]
