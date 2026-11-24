import django.db.models.deletion
from django.db import migrations, models

SQL='\n'.join(f'CREATE TRIGGER business_scope BEFORE INSERT OR UPDATE ON erp_{table} FOR EACH ROW EXECUTE FUNCTION erp_guard_business();' for table in ('crmopportunity','crmevent','crmactivity'))+'\n'+ '\n'.join(f'CREATE TRIGGER source_immutable BEFORE UPDATE OR DELETE ON erp_{table} FOR EACH ROW EXECUTE FUNCTION erp_guard_source_record();' for table in ('crmopportunity','crmevent'))+'''
CREATE FUNCTION erp_guard_crm_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE kind text; original_date date; linked_opportunity bigint; linked_location bigint;
BEGIN
 SELECT d.kind,d.date INTO kind,original_date FROM erp_document d WHERE d.id=NEW.source_id AND d.business_id=NEW.business_id AND d.state='draft';
 IF kind IS NULL THEN RAISE EXCEPTION 'CRM evidence needs an original draft operation document'; END IF;
 IF TG_TABLE_NAME='erp_crmopportunity' THEN
  IF kind<>'crm_create' OR NEW.expected_amount<0 OR NEW.expected_date<original_date OR jsonb_typeof(NEW.product_lines)<>'array' OR jsonb_array_length(NEW.product_lines)=0 OR NOT (NEW.product_lines <@ '["sponge","adhesive","shared"]'::jsonb) THEN RAISE EXCEPTION 'Invalid original CRM opportunity'; END IF;
 ELSE
  SELECT location_id INTO linked_location FROM erp_crmopportunity WHERE id=NEW.opportunity_id;
  IF TG_TABLE_NAME='erp_crmevent' THEN
   IF NOT ((NEW.kind='stage' AND kind='crm_transition' AND NEW.stage IN ('new','qualified','quoted','negotiation','won','lost') AND NEW.reason<>'' AND NEW.assigned_id IS NULL AND NEW.quotation_id IS NULL)
     OR (NEW.kind='assignment' AND kind='crm_assign' AND NEW.assigned_id IS NOT NULL AND NEW.stage='' AND NEW.quotation_id IS NULL AND NEW.reason<>'')
     OR (NEW.kind='note' AND kind='crm_note' AND NEW.stage='' AND NEW.assigned_id IS NULL AND NEW.quotation_id IS NULL AND NEW.reason<>'')
     OR (NEW.kind='quotation' AND kind='crm_quote' AND NEW.stage='' AND NEW.assigned_id IS NULL AND NEW.quotation_id IS NOT NULL)) THEN RAISE EXCEPTION 'Invalid CRM event shape/source'; END IF;
   IF NEW.quotation_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM erp_document q WHERE q.id=NEW.quotation_id AND q.kind='quotation' AND q.state='posted' AND q.location_id=linked_location AND q.data->>'crm_opportunity'=NEW.opportunity_id::text) THEN RAISE EXCEPTION 'CRM quotation must retain its original opportunity and location'; END IF;
  ELSIF kind<>'crm_activity' OR NEW.due_date<original_date OR NEW.completed_by_id IS NOT NULL THEN RAISE EXCEPTION 'Invalid original CRM activity'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER crm_evidence BEFORE INSERT ON erp_crmopportunity FOR EACH ROW EXECUTE FUNCTION erp_guard_crm_evidence();
CREATE TRIGGER crm_evidence BEFORE INSERT ON erp_crmevent FOR EACH ROW EXECUTE FUNCTION erp_guard_crm_evidence();
CREATE TRIGGER crm_evidence BEFORE INSERT ON erp_crmactivity FOR EACH ROW EXECUTE FUNCTION erp_guard_crm_evidence();
CREATE FUNCTION erp_guard_crm_activity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' OR (NEW.business_id,NEW.opportunity_id,NEW.assigned_id,NEW.due_date,NEW.task,NEW.source_id) IS DISTINCT FROM (OLD.business_id,OLD.opportunity_id,OLD.assigned_id,OLD.due_date,OLD.task,OLD.source_id) THEN RAISE EXCEPTION 'CRM follow-up evidence is immutable'; END IF;
 IF OLD.completed_by_id IS NOT NULL AND NEW.completed_by_id IS DISTINCT FROM OLD.completed_by_id THEN RAISE EXCEPTION 'Completed CRM activity cannot reopen'; END IF;
 IF NEW.completed_by_id IS DISTINCT FROM OLD.completed_by_id AND NOT EXISTS (SELECT 1 FROM erp_document d JOIN erp_document original ON original.id=OLD.source_id WHERE d.id=NEW.completed_by_id AND d.business_id=NEW.business_id AND d.kind='crm_activity_done' AND d.state='draft' AND d.date>=original.date AND d.data->>'activity'=NEW.id::text) THEN RAISE EXCEPTION 'CRM completion requires original operation evidence'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER crm_activity_immutable BEFORE UPDATE OR DELETE ON erp_crmactivity FOR EACH ROW EXECUTE FUNCTION erp_guard_crm_activity();
CREATE FUNCTION erp_guard_crm_document() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.state='posted' AND NEW.kind='crm_create' AND NOT EXISTS(SELECT 1 FROM erp_crmopportunity o WHERE o.source_id=NEW.id AND o.location_id=NEW.location_id AND o.product_lines=to_jsonb(NEW.product_lines)) THEN RAISE EXCEPTION 'Posted CRM opportunity must retain original location and full product-line scope'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER crm_document_scope AFTER INSERT OR UPDATE OF state ON erp_document FOR EACH ROW EXECUTE FUNCTION erp_guard_crm_document();
'''


class Migration(migrations.Migration):
    dependencies=[('erp','0027_supplier_quotes')]
    operations=[
        migrations.CreateModel(name='CRMOpportunity',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('title',models.CharField(max_length=180)),('product_lines',models.JSONField(default=list)),('prospect_name',models.CharField(max_length=180)),('phone',models.CharField(blank=True,max_length=80)),
            ('expected_amount',models.DecimalField(decimal_places=2,max_digits=20)),('expected_date',models.DateField()),('note',models.TextField(blank=True)),
            ('business',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.business')),
            ('location',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.location')),
            ('assigned',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.membership')),
            ('party',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,to='erp.party')),
            ('source',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,to='erp.document')),
        ]),
        migrations.CreateModel(name='CRMEvent',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('kind',models.CharField(max_length=20)),('stage',models.CharField(blank=True,max_length=20)),('reason',models.TextField(blank=True)),
            ('business',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.business')),
            ('opportunity',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='events',to='erp.crmopportunity')),
            ('assigned',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,to='erp.membership')),
            ('quotation',models.OneToOneField(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,related_name='crm_link',to='erp.document')),
            ('source',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,to='erp.document')),
        ],options={'ordering':['id']}),
        migrations.CreateModel(name='CRMActivity',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('due_date',models.DateField()),('task',models.CharField(max_length=500)),
            ('business',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.business')),
            ('opportunity',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='activities',to='erp.crmopportunity')),
            ('assigned',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.membership')),
            ('source',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,to='erp.document')),
            ('completed_by',models.OneToOneField(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,related_name='+',to='erp.document')),
        ]),
        migrations.RunSQL(SQL),
    ]
