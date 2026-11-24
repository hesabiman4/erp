import django.db.models.deletion
from django.db import migrations,models

SQL='\n'.join(f'CREATE TRIGGER business_scope BEFORE INSERT OR UPDATE ON erp_{name} FOR EACH ROW EXECUTE FUNCTION erp_guard_business();' for name in ['documentcapture','capturereview'])+r'''
CREATE TRIGGER capture_source_immutable BEFORE UPDATE OR DELETE ON erp_documentcapture FOR EACH ROW EXECUTE FUNCTION erp_guard_source_record();
CREATE FUNCTION erp_guard_capture_review() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Capture reviews are immutable evidence'; END IF;
 IF TG_OP='UPDATE' THEN
  IF (NEW.business_id,NEW.capture_id,NEW.outcome,NEW.reason,NEW.approved_data,NEW.supplier_id,NEW.supplier_reference,NEW.draft_id,NEW.source_id)
     IS DISTINCT FROM (OLD.business_id,OLD.capture_id,OLD.outcome,OLD.reason,OLD.approved_data,OLD.supplier_id,OLD.supplier_reference,OLD.draft_id,OLD.source_id)
     OR OLD.posted_document_id IS NOT NULL OR NEW.posted_document_id IS NULL THEN RAISE EXCEPTION 'Only first reviewed posting may bind a capture review'; END IF;
 END IF;
 IF NEW.outcome NOT IN ('draft','rejected') OR (NEW.outcome='draft' AND NEW.draft_id IS NULL) OR (NEW.outcome='rejected' AND (NEW.draft_id IS NOT NULL OR NEW.posted_document_id IS NOT NULL)) THEN RAISE EXCEPTION 'Invalid capture review state'; END IF;
 IF NEW.posted_document_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM erp_document d WHERE d.id=NEW.posted_document_id AND d.business_id=NEW.business_id AND d.kind IN ('expense_post','purchase_bill') AND d.state='draft' AND d.data=NEW.approved_data) THEN RAISE EXCEPTION 'Capture posting must be original reviewed ordinary transaction'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER capture_review_immutable BEFORE INSERT OR UPDATE OR DELETE ON erp_capturereview FOR EACH ROW EXECUTE FUNCTION erp_guard_capture_review();
'''

class Migration(migrations.Migration):
    dependencies=[('erp','0028_crm')]
    operations=[
        migrations.CreateModel(name='DocumentCapture',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('filename',models.CharField(max_length=200)),('media_type',models.CharField(max_length=40)),('sha256',models.CharField(max_length=64)),('original',models.BinaryField()),('preview',models.BinaryField()),
            ('extracted_text',models.TextField()),('suggestions',models.JSONField(default=dict)),('extraction',models.JSONField(default=dict)),
            ('business',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.business')),
            ('location',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.location')),
            ('source',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,to='erp.document')),
        ],options={'constraints':[models.UniqueConstraint(fields=('business','sha256'),name='capture_original_once')]}),
        migrations.CreateModel(name='CaptureReview',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('outcome',models.CharField(max_length=12)),('reason',models.TextField()),('approved_data',models.JSONField(default=dict)),('supplier_reference',models.CharField(blank=True,max_length=150)),
            ('business',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.business')),
            ('capture',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,related_name='review',to='erp.documentcapture')),
            ('supplier',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,to='erp.party')),
            ('draft',models.OneToOneField(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,related_name='+',to='erp.document')),
            ('posted_document',models.OneToOneField(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,related_name='+',to='erp.document')),
            ('source',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,to='erp.document')),
        ],options={'constraints':[models.UniqueConstraint(fields=('business','supplier','supplier_reference'),condition=models.Q(supplier__isnull=False)&~models.Q(supplier_reference=''),name='capture_supplier_reference_once')]}),
        migrations.RunSQL(SQL),
    ]
