from django.db import migrations,models
import django.db.models.deletion

REVERSAL_SQL=r'''
CREATE OR REPLACE FUNCTION erp_guard_allocation_sign() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_record erp_document%ROWTYPE; source_record erp_document%ROWTYPE;
 original_amount numeric; compensated numeric; exposure_key bigint;
 source_quantity numeric; source_value numeric; source_movement bigint;
BEGIN
 IF NEW.amount>=0 THEN RETURN NEW; END IF;
 SELECT * INTO owner_record FROM erp_document WHERE id=NEW.document_id;
 IF owner_record.kind NOT IN ('payment_reverse','fx_settlement_reverse') OR owner_record.reference_id IS NULL THEN
  RAISE EXCEPTION 'Negative allocation requires a supported linked full payment reversal';
 END IF;
 SELECT * INTO source_record FROM erp_document WHERE id=owner_record.reference_id;
 IF source_record.state<>'posted' OR source_record.business_id<>owner_record.business_id OR owner_record.date<source_record.date THEN
  RAISE EXCEPTION 'Reversal must reference an earlier posted payment in the same business';
 END IF;
 IF (owner_record.kind='payment_reverse' AND source_record.kind NOT IN ('receipt','supplier_payment')) OR
    (owner_record.kind='fx_settlement_reverse' AND source_record.kind<>'fx_settle') THEN
  RAISE EXCEPTION 'Unsupported source payment kind for compensating allocation';
 END IF;
 SELECT COALESCE(SUM(a.amount),0) INTO original_amount FROM erp_allocation a
  WHERE a.document_id=source_record.id AND a.invoice_id=NEW.invoice_id AND a.amount>0;
 IF original_amount<=0 OR NEW.amount<>-original_amount THEN
  RAISE EXCEPTION 'Compensating allocation must mirror the full original invoice allocation';
 END IF;
 SELECT COALESCE(SUM(-a.amount),0) INTO compensated FROM erp_allocation a JOIN erp_document d ON d.id=a.document_id
  WHERE d.reference_id=source_record.id AND d.kind IN ('payment_reverse','fx_settlement_reverse')
   AND a.invoice_id=NEW.invoice_id AND a.amount<0 AND a.id IS DISTINCT FROM NEW.id;
 IF compensated-NEW.amount>original_amount THEN RAISE EXCEPTION 'Original allocation has already been compensated'; END IF;
 IF EXISTS (
  SELECT e.account_id,e.credit,e.debit,e.location_id,e.warehouse_id,e.party_id,e.employee_id,e.line
   FROM erp_entry e WHERE e.document_id=source_record.id
  EXCEPT ALL
  SELECT r.account_id,r.debit,r.credit,r.location_id,r.warehouse_id,r.party_id,r.employee_id,r.line
   FROM erp_entry r WHERE r.document_id=owner_record.id
 ) OR EXISTS (
  SELECT r.account_id,r.debit,r.credit,r.location_id,r.warehouse_id,r.party_id,r.employee_id,r.line
   FROM erp_entry r WHERE r.document_id=owner_record.id
  EXCEPT ALL
  SELECT e.account_id,e.credit,e.debit,e.location_id,e.warehouse_id,e.party_id,e.employee_id,e.line
   FROM erp_entry e WHERE e.document_id=source_record.id
 ) THEN
  RAISE EXCEPTION 'Compensating allocation requires the original mirrored journal';
 END IF;
 IF owner_record.kind='fx_settlement_reverse' THEN
  IF source_record.reference_id IS DISTINCT FROM NEW.invoice_id THEN RAISE EXCEPTION 'Foreign settlement belongs to another invoice'; END IF;
  SELECT m.id,m.exposure_id,m.quantity,m.base_value INTO source_movement,exposure_key,source_quantity,source_value
   FROM erp_foreignmovement m WHERE m.document_id=source_record.id AND m.kind='settlement' AND m.quantity<0 LIMIT 1;
  IF source_movement IS NULL OR NOT EXISTS (
   SELECT 1 FROM erp_foreignmovement m WHERE m.document_id=owner_record.id AND m.exposure_id=exposure_key
    AND m.kind='reversal' AND m.quantity=-source_quantity AND m.base_value=-source_value) THEN
   RAISE EXCEPTION 'Foreign reversal requires its exact compensating exposure movement';
  END IF;
  IF EXISTS(SELECT 1 FROM erp_foreignmovement m JOIN erp_document d ON d.id=m.document_id
   WHERE m.exposure_id=exposure_key AND m.id>source_movement AND d.state='posted' AND d.id<>owner_record.id) THEN
   RAISE EXCEPTION 'Later foreign invoice movements prevent exact settlement reversal';
  END IF;
  IF EXISTS(SELECT 1 FROM erp_foreignwalletmovement w WHERE w.document_id=source_record.id AND (
   NOT EXISTS(SELECT 1 FROM erp_foreignwalletmovement r WHERE r.document_id=owner_record.id
    AND r.wallet_id=w.wallet_id AND r.quantity=-w.quantity AND r.base_value=-w.base_value)
   OR EXISTS(SELECT 1 FROM erp_foreignwalletmovement later JOIN erp_document d ON d.id=later.document_id
    WHERE later.wallet_id=w.wallet_id AND later.id>w.id AND d.state='posted' AND d.id<>owner_record.id))) THEN
   RAISE EXCEPTION 'Foreign reversal requires an exact latest wallet movement';
  END IF;
 END IF;
 RETURN NEW;
END $$;
'''


def seed(apps,schema_editor):
    Account=apps.get_model('erp','Account')
    for business in apps.get_model('erp','Business').objects.all():
        for code,name,category,number,group in [('FX_CUSTOMER_DEPOSITS','Refundable foreign customer deposits','liability','21310','current_liabilities'),('FX_SUPPLIER_DEPOSITS','Refundable foreign supplier deposits','asset','11310','current_assets')]:
            Account.objects.get_or_create(business_id=business.id,code=code,defaults={'name':name,'category':category,'number':number,'statement_group':group,'control':True})


class Migration(migrations.Migration):
    dependencies=[('erp','0014_order_cutting')]
    operations=[
        migrations.CreateModel(name='ForeignDeposit',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('currency',models.CharField(max_length=3,choices=[('USD','US dollar'),('PKR','Pakistani rupee')])),
            ('side',models.CharField(max_length=8,choices=[('customer','Customer liability'),('supplier','Supplier asset')])),
            ('foreign_amount',models.DecimalField(max_digits=20,decimal_places=2)),
            ('base_value',models.DecimalField(max_digits=20,decimal_places=2)),
            ('business',models.ForeignKey(to='erp.business',on_delete=django.db.models.deletion.PROTECT)),
            ('party',models.ForeignKey(to='erp.party',on_delete=django.db.models.deletion.PROTECT)),
            ('location',models.ForeignKey(to='erp.location',on_delete=django.db.models.deletion.PROTECT)),
            ('source',models.OneToOneField(to='erp.document',on_delete=django.db.models.deletion.PROTECT,related_name='foreign_deposit')),
        ],options={'constraints':[models.CheckConstraint(condition=models.Q(foreign_amount__gt=0,base_value__gte=0),name='fx_deposit_positive')]}),
        migrations.CreateModel(name='ForeignDepositMovement',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('quantity',models.DecimalField(max_digits=20,decimal_places=2,default=0)),
            ('base_value',models.DecimalField(max_digits=20,decimal_places=2)),
            ('kind',models.CharField(max_length=16)),
            ('business',models.ForeignKey(to='erp.business',on_delete=django.db.models.deletion.PROTECT)),
            ('deposit',models.ForeignKey(to='erp.foreigndeposit',on_delete=django.db.models.deletion.PROTECT,related_name='movements')),
            ('document',models.ForeignKey(to='erp.document',on_delete=django.db.models.deletion.PROTECT)),
        ]),
        migrations.RunPython(seed,migrations.RunPython.noop),
        migrations.RunSQL('''
CREATE TRIGGER business_scope BEFORE INSERT OR UPDATE ON erp_foreigndeposit FOR EACH ROW EXECUTE FUNCTION erp_guard_business();
CREATE TRIGGER business_scope BEFORE INSERT OR UPDATE ON erp_foreigndepositmovement FOR EACH ROW EXECUTE FUNCTION erp_guard_business();
CREATE TRIGGER source_immutable BEFORE UPDATE OR DELETE ON erp_foreigndeposit FOR EACH ROW EXECUTE FUNCTION erp_guard_source_record();
CREATE TRIGGER ledger_immutable BEFORE INSERT OR UPDATE OR DELETE ON erp_foreigndepositmovement FOR EACH ROW EXECUTE FUNCTION erp_guard_ledger_row();
''',reverse_sql='''DROP TRIGGER IF EXISTS ledger_immutable ON erp_foreigndepositmovement;DROP TRIGGER IF EXISTS source_immutable ON erp_foreigndeposit;DROP TRIGGER IF EXISTS business_scope ON erp_foreigndepositmovement;DROP TRIGGER IF EXISTS business_scope ON erp_foreigndeposit;'''),
        migrations.RunSQL(REVERSAL_SQL),
    ]
