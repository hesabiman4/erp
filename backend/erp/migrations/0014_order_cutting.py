from django.db import migrations,models
import django.db.models.deletion

SQL=r'''
CREATE TRIGGER business_scope BEFORE INSERT OR UPDATE ON erp_ordercutdemand FOR EACH ROW EXECUTE FUNCTION erp_guard_business();
CREATE TRIGGER business_scope BEFORE INSERT OR UPDATE ON erp_ordercutsheet FOR EACH ROW EXECUTE FUNCTION erp_guard_business();
CREATE FUNCTION erp_guard_order_cut_demand() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_plan erp_cutplan%ROWTYPE; parent_order erp_document%ROWTYPE; source_line jsonb;
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Order cutting history cannot be deleted'; END IF;
 IF TG_OP='UPDATE' THEN
  IF (NEW.business_id,NEW.plan_id,NEW.order_id,NEW.order_index,NEW.thickness_mm,NEW.sheet_count,NEW.quantity_cm) IS DISTINCT FROM (OLD.business_id,OLD.plan_id,OLD.order_id,OLD.order_index,OLD.thickness_mm,OLD.sheet_count,OLD.quantity_cm) THEN RAISE EXCEPTION 'Order cutting demand dimensions are immutable'; END IF;
  IF NEW.state IS DISTINCT FROM OLD.state AND NOT ((OLD.state='planned' AND NEW.state IN ('cut','cancelled')) OR (OLD.state='cut' AND NEW.state='cancelled')) THEN RAISE EXCEPTION 'A disposed cutting demand cannot reopen'; END IF;
 END IF;
 SELECT * INTO parent_plan FROM erp_cutplan WHERE id=NEW.plan_id;
 SELECT * INTO parent_order FROM erp_document WHERE id=NEW.order_id;
 source_line=parent_order.result->'lines'->NEW.order_index;
 IF parent_order.kind<>'sales_order' OR parent_order.state<>'posted' OR parent_plan.warehouse_id IS DISTINCT FROM parent_order.warehouse_id OR source_line IS NULL OR (source_line->>'product')::bigint IS DISTINCT FROM parent_plan.product_id OR (COALESCE(source_line->>'profile','')<>'' AND source_line->>'profile' IS DISTINCT FROM parent_plan.profile) OR NEW.quantity_cm<>NEW.thickness_mm*NEW.sheet_count/10 THEN RAISE EXCEPTION 'Cut demand must match its sales-order product, warehouse and footprint'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER demand_dimensions BEFORE INSERT OR UPDATE OR DELETE ON erp_ordercutdemand FOR EACH ROW EXECUTE FUNCTION erp_guard_order_cut_demand();
CREATE FUNCTION erp_guard_order_cut_sheet() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE demand erp_ordercutdemand%ROWTYPE; parent_plan erp_cutplan%ROWTYPE; piece erp_block%ROWTYPE; posting erp_document%ROWTYPE; existing_count bigint;
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Order-linked sheet history cannot be deleted'; END IF;
 IF TG_OP='UPDATE' THEN
  IF (NEW.business_id,NEW.demand_id,NEW.block_id,NEW.quantity_cm) IS DISTINCT FROM (OLD.business_id,OLD.demand_id,OLD.block_id,OLD.quantity_cm) THEN RAISE EXCEPTION 'Held-sheet provenance is immutable'; END IF;
  IF (OLD.fulfilled_document_id IS NOT NULL AND NEW.fulfilled_document_id IS DISTINCT FROM OLD.fulfilled_document_id) OR (OLD.released_by_id IS NOT NULL AND NEW.released_by_id IS DISTINCT FROM OLD.released_by_id) THEN RAISE EXCEPTION 'Held-sheet disposition cannot be reopened'; END IF;
 END IF;
 SELECT * INTO demand FROM erp_ordercutdemand WHERE id=NEW.demand_id;
 SELECT * INTO parent_plan FROM erp_cutplan WHERE id=demand.plan_id;
 SELECT * INTO piece FROM erp_block WHERE id=NEW.block_id;
 IF piece.product_id IS DISTINCT FROM parent_plan.product_id OR piece.profile IS DISTINCT FROM parent_plan.profile OR piece.warehouse_id IS DISTINCT FROM parent_plan.warehouse_id OR NEW.quantity_cm<>demand.thickness_mm/10 THEN RAISE EXCEPTION 'Held sheet dimensions do not match cut demand'; END IF;
 IF TG_OP='INSERT' THEN
  SELECT count(*) INTO existing_count FROM erp_ordercutsheet WHERE demand_id=NEW.demand_id;
  IF existing_count>=demand.sheet_count THEN RAISE EXCEPTION 'Held-sheet count exceeds approved cutting demand'; END IF;
 END IF;
 IF NEW.fulfilled_document_id IS NOT NULL AND (TG_OP='INSERT' OR NEW.fulfilled_document_id IS DISTINCT FROM OLD.fulfilled_document_id) THEN
  SELECT * INTO posting FROM erp_document WHERE id=NEW.fulfilled_document_id;
  IF posting.kind<>'sale' OR posting.state<>'draft' THEN RAISE EXCEPTION 'Fulfillment must be set while posting a sales invoice'; END IF;
 END IF;
 IF NEW.released_by_id IS NOT NULL AND (TG_OP='INSERT' OR NEW.released_by_id IS DISTINCT FROM OLD.released_by_id) THEN
  SELECT * INTO posting FROM erp_document WHERE id=NEW.released_by_id;
  IF posting.kind<>'cut_execute' OR posting.state<>'draft' THEN RAISE EXCEPTION 'Release must be set while posting a cut-plan disposition'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER sheet_provenance BEFORE INSERT OR UPDATE OR DELETE ON erp_ordercutsheet FOR EACH ROW EXECUTE FUNCTION erp_guard_order_cut_sheet();
CREATE FUNCTION erp_guard_linked_cut_plan() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM erp_ordercutdemand WHERE plan_id=OLD.id) THEN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Order-linked cut plans cannot be deleted'; END IF;
  IF EXISTS(SELECT 1 FROM erp_document WHERE id=OLD.source_id AND state='posted') AND (NEW.business_id,NEW.warehouse_id,NEW.product_id,NEW.profile,NEW.allocations,NEW.reservation_id,NEW.source_id) IS DISTINCT FROM (OLD.business_id,OLD.warehouse_id,OLD.product_id,OLD.profile,OLD.allocations,OLD.reservation_id,OLD.source_id) THEN RAISE EXCEPTION 'Order-linked cut plan dimensions are immutable'; END IF;
  IF OLD.state IN ('executed','cancelled') AND (NEW.state,NEW.completed_by_id) IS DISTINCT FROM (OLD.state,OLD.completed_by_id) THEN RAISE EXCEPTION 'A completed order-linked cutting plan cannot reopen'; END IF;
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER linked_plan_history BEFORE UPDATE OR DELETE ON erp_cutplan FOR EACH ROW EXECUTE FUNCTION erp_guard_linked_cut_plan();
'''

class Migration(migrations.Migration):
    dependencies=[('erp','0013_default_jalali_calendar')]
    operations=[
        migrations.CreateModel(name='OrderCutDemand',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('order_index',models.PositiveIntegerField()),('thickness_mm',models.DecimalField(max_digits=18,decimal_places=3)),('sheet_count',models.PositiveIntegerField()),('quantity_cm',models.DecimalField(max_digits=24,decimal_places=6)),
            ('state',models.CharField(max_length=12,default='planned',choices=[('planned','Planned'),('cut','Cut'),('cancelled','Cancelled')])),
            ('business',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.business')),
            ('order',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.document',related_name='cut_demands')),
            ('plan',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.cutplan',related_name='order_demands')),
        ],options={'constraints':[models.CheckConstraint(condition=models.Q(thickness_mm__gt=0,sheet_count__gt=0,quantity_cm__gt=0),name='order_cut_demand_positive')],'indexes':[models.Index(fields=['business','order','order_index','state'],name='order_cut_demand_scope')]}),
        migrations.CreateModel(name='OrderCutSheet',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('quantity_cm',models.DecimalField(max_digits=24,decimal_places=6)),
            ('business',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.business')),
            ('block',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,to='erp.block',related_name='order_cut_sheet')),
            ('demand',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.ordercutdemand',related_name='sheets')),
            ('fulfilled_document',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,to='erp.document',related_name='fulfilled_cut_sheets')),
            ('released_by',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,to='erp.document',related_name='released_cut_sheets')),
        ],options={'constraints':[models.CheckConstraint(condition=models.Q(quantity_cm__gt=0),name='order_cut_sheet_positive'),models.CheckConstraint(condition=models.Q(fulfilled_document__isnull=True)|models.Q(released_by__isnull=True),name='order_cut_sheet_one_disposition')]}),
        migrations.RunSQL(SQL,'DROP FUNCTION IF EXISTS erp_guard_linked_cut_plan() CASCADE; DROP FUNCTION IF EXISTS erp_guard_order_cut_sheet() CASCADE; DROP FUNCTION IF EXISTS erp_guard_order_cut_demand() CASCADE; DROP TRIGGER IF EXISTS business_scope ON erp_ordercutdemand; DROP TRIGGER IF EXISTS business_scope ON erp_ordercutsheet;'),
    ]
