import django.db.models.deletion
from django.db import migrations,models


SQL='\n'.join(f'CREATE TRIGGER business_scope BEFORE INSERT OR UPDATE ON erp_{name} FOR EACH ROW EXECUTE FUNCTION erp_guard_business();' for name in ['statementimport','statementrow','statementreview','statementmatch','statementreconciliation'])+'\n'+ '\n'.join(f'CREATE TRIGGER source_immutable BEFORE UPDATE OR DELETE ON erp_{name} FOR EACH ROW EXECUTE FUNCTION erp_guard_source_record();' for name in ['statementimport','statementreview','statementreconciliation'])+r'''
CREATE FUNCTION erp_guard_statement_row() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Imported statement transactions are immutable; preserve source evidence and append review events'; END $$;
CREATE TRIGGER statement_row_immutable BEFORE UPDATE OR DELETE ON erp_statementrow FOR EACH ROW EXECUTE FUNCTION erp_guard_statement_row();
CREATE FUNCTION erp_guard_statement_review_entry() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual_business bigint;
BEGIN
 IF NEW.entry_id IS NOT NULL THEN
  SELECT d.business_id INTO actual_business FROM erp_entry e JOIN erp_document d ON d.id=e.document_id WHERE e.id=NEW.entry_id;
  IF actual_business IS DISTINCT FROM NEW.business_id THEN RAISE EXCEPTION 'Statement entry belongs to another business'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER statement_entry_tenant BEFORE INSERT OR UPDATE ON erp_statementreview FOR EACH ROW EXECUTE FUNCTION erp_guard_statement_review_entry();
CREATE FUNCTION erp_guard_statement_match() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE valid boolean;
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Release a statement match through an audited event'; END IF;
 IF TG_OP='UPDATE' THEN
  IF (NEW.business_id,NEW.row_id,NEW.entry_id,NEW.source_id) IS DISTINCT FROM (OLD.business_id,OLD.row_id,OLD.entry_id,OLD.source_id) OR OLD.released_by_id IS NOT NULL OR NEW.released_by_id IS NULL THEN
   RAISE EXCEPTION 'Statement match dimensions/history cannot change';
  END IF;
 END IF;
 SELECT EXISTS(SELECT 1 FROM erp_statementrow r JOIN erp_statementimport s ON s.id=r.statement_id JOIN erp_entry e ON e.id=NEW.entry_id JOIN erp_document d ON d.id=e.document_id
 WHERE r.id=NEW.row_id AND r.business_id=NEW.business_id AND d.business_id=NEW.business_id AND d.state='posted' AND s.source_type='bank' AND s.account_id=e.account_id AND s.location_id=e.location_id AND e.debit-e.credit=r.amount AND d.date BETWEEN s.starts AND s.ends AND ABS(d.date-r.date)<=7) INTO valid;
 IF NOT valid THEN RAISE EXCEPTION 'Statement match must reference an exact eligible same-business BANK movement'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER statement_match_guard BEFORE INSERT OR UPDATE OR DELETE ON erp_statementmatch FOR EACH ROW EXECUTE FUNCTION erp_guard_statement_match();
'''


class Migration(migrations.Migration):
    dependencies=[('erp','0025_cashier_shifts')]
    operations=[
        migrations.CreateModel(name='StatementImport',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('source_type',models.CharField(max_length=8)),('institution',models.CharField(max_length=150)),('account_reference',models.CharField(max_length=100)),
            ('currency',models.CharField(default='AFN',max_length=3)),('starts',models.DateField()),('ends',models.DateField()),
            ('opening_balance',models.DecimalField(decimal_places=2,max_digits=20)),('closing_balance',models.DecimalField(decimal_places=2,max_digits=20)),
            ('filename',models.CharField(max_length=200)),('sha256',models.CharField(max_length=64)),('original',models.BinaryField()),
            ('business',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.business')),
            ('location',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.location')),
            ('account',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,to='erp.account')),
            ('source',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,to='erp.document')),
        ],options={'constraints':[models.UniqueConstraint(fields=('business','location','source_type','account_reference','sha256'),name='statement_file_once'),models.CheckConstraint(condition=models.Q(('starts__lte',models.F('ends'))),name='statement_date_window')]}),
        migrations.CreateModel(name='StatementRow',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('position',models.PositiveIntegerField()),('date',models.DateField()),('reference',models.CharField(blank=True,max_length=150)),
            ('description',models.CharField(max_length=1000)),('amount',models.DecimalField(decimal_places=2,max_digits=20)),('fingerprint',models.CharField(max_length=64)),
            ('business',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.business')),
            ('statement',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='rows',to='erp.statementimport')),
        ],options={'constraints':[models.UniqueConstraint(fields=('statement','position'),name='statement_position_once'),models.UniqueConstraint(fields=('business','fingerprint'),name='statement_row_once'),models.CheckConstraint(condition=~models.Q(amount=0),name='statement_row_nonzero')]}),
        migrations.CreateModel(name='StatementReview',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('outcome',models.CharField(max_length=12)),('note',models.TextField()),
            ('business',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.business')),
            ('row',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='reviews',to='erp.statementrow')),
            ('entry',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,to='erp.entry')),
            ('source',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,to='erp.document')),
        ]),
        migrations.CreateModel(name='StatementMatch',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('business',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.business')),
            ('row',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='matches',to='erp.statementrow')),
            ('entry',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.entry')),
            ('source',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,to='erp.document')),
            ('released_by',models.OneToOneField(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,related_name='+',to='erp.document')),
        ],options={'constraints':[models.UniqueConstraint(fields=('business','entry'),condition=models.Q(released_by__isnull=True),name='statement_entry_active_once'),models.UniqueConstraint(fields=('row',),condition=models.Q(released_by__isnull=True),name='statement_row_active_once')]}),
        migrations.CreateModel(name='StatementReconciliation',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('business',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.business')),
            ('statement',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,related_name='reconciliation',to='erp.statementimport')),
            ('bank_document',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,related_name='+',to='erp.document')),
            ('source',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,to='erp.document')),
        ]),
        migrations.RunSQL(SQL),
    ]
