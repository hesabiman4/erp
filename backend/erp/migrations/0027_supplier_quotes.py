import django.db.models.deletion
from django.db import migrations,models


class Migration(migrations.Migration):
    dependencies=[('erp','0026_statement_imports')]
    operations=[
        migrations.CreateModel(name='SourcingRequest',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('desired_date',models.DateField()),('lines',models.JSONField(default=list)),('note',models.TextField(blank=True)),('state',models.CharField(default='open',max_length=16)),
            ('business',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.business')),
            ('warehouse',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.warehouse')),
            ('source',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,to='erp.document')),
            ('closed_by',models.OneToOneField(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,related_name='+',to='erp.document')),
        ]),
        migrations.CreateModel(name='SupplierOffer',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('reference',models.CharField(max_length=150)),('valid_through',models.DateField()),('lead_days',models.PositiveSmallIntegerField()),('payment_terms',models.CharField(max_length=250)),('lines',models.JSONField(default=list)),
            ('freight_estimate',models.DecimalField(decimal_places=2,max_digits=20)),('merchandise_total',models.DecimalField(decimal_places=2,max_digits=20)),('comparison_total',models.DecimalField(decimal_places=2,max_digits=20)),('currency',models.CharField(default='AFN',max_length=3)),('note',models.TextField(blank=True)),
            ('business',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.business')),
            ('request',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='offers',to='erp.sourcingrequest')),
            ('supplier',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.party')),
            ('source',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,to='erp.document')),
        ]),
        migrations.CreateModel(name='SourcingAward',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('reason',models.TextField()),
            ('business',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.business')),
            ('request',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,related_name='award',to='erp.sourcingrequest')),
            ('offer',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,related_name='award',to='erp.supplieroffer')),
            ('purchase_order',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,related_name='sourcing_award',to='erp.document')),
            ('source',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,to='erp.document')),
        ]),
        migrations.AddConstraint(model_name='supplieroffer',constraint=models.UniqueConstraint(fields=('business','request','supplier','reference'),name='supplier_offer_reference_scope')),
        migrations.AddConstraint(model_name='supplieroffer',constraint=models.CheckConstraint(condition=models.Q(freight_estimate__gte=0,merchandise_total__gte=0,comparison_total__gte=0),name='supplier_offer_amounts_nonnegative')),
        migrations.RunSQL('\n'.join(f'CREATE TRIGGER business_scope BEFORE INSERT OR UPDATE ON erp_{name} FOR EACH ROW EXECUTE FUNCTION erp_guard_business();' for name in ['sourcingrequest','supplieroffer','sourcingaward'])),
        migrations.RunSQL('\n'.join(f'CREATE TRIGGER source_immutable BEFORE UPDATE OR DELETE ON erp_{name} FOR EACH ROW EXECUTE FUNCTION erp_guard_source_record();' for name in ['supplieroffer','sourcingaward'])),
        migrations.RunSQL('''
CREATE FUNCTION erp_guard_sourcing_request() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' OR (NEW.business_id,NEW.warehouse_id,NEW.desired_date,NEW.lines,NEW.note,NEW.source_id) IS DISTINCT FROM (OLD.business_id,OLD.warehouse_id,OLD.desired_date,OLD.lines,OLD.note,OLD.source_id) THEN RAISE EXCEPTION 'Sourcing request evidence is immutable; close it and create a new request'; END IF;
 IF OLD.state <> 'open' AND (NEW.state,NEW.closed_by_id) IS DISTINCT FROM (OLD.state,OLD.closed_by_id) THEN RAISE EXCEPTION 'Closed sourcing request cannot reopen'; END IF;
 IF NEW.state NOT IN ('open','awarded','cancelled') OR (NEW.state='open' AND NEW.closed_by_id IS NOT NULL) OR (NEW.state<>'open' AND NEW.closed_by_id IS NULL) THEN RAISE EXCEPTION 'Sourcing request closure requires source evidence'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER sourcing_immutable BEFORE UPDATE OR DELETE ON erp_sourcingrequest FOR EACH ROW EXECUTE FUNCTION erp_guard_sourcing_request();
'''),
    ]
