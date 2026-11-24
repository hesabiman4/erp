from django.db import migrations

ACCOUNTS={
 'FX_CASH':('Foreign currency cash','asset','10010','current_assets',True),
 'FX_BANK':('Foreign currency bank','asset','10110','current_assets',True),
 'FX_TRANSIT':('Remittances in transit','asset','10200','current_assets',True),
 'FX_GAIN':('Foreign exchange gains','income','43000','other_operating_income',False),
 'FX_LOSS':('Foreign exchange losses','expense','64200','other_operating_expenses',False),
}
def seed(apps,schema_editor):
    Account=apps.get_model('erp','Account')
    for business in apps.get_model('erp','Business').objects.all():
        for code,(name,category,number,group,control) in ACCOUNTS.items():
            Account.objects.get_or_create(business_id=business.id,code=code,defaults={'name':name,'category':category,'number':number,'statement_group':group,'control':control})

SQL=''
for table in ['exchangerate','foreignexposure','foreignmovement','foreignwallet','foreignwalletmovement','remittance','remittanceadjustment']:
    SQL+=f'CREATE TRIGGER business_scope BEFORE INSERT OR UPDATE ON erp_{table} FOR EACH ROW EXECUTE FUNCTION erp_guard_business();\n'
for table in ['foreignmovement','foreignwalletmovement','remittanceadjustment']:
    SQL+=f'CREATE TRIGGER ledger_immutable BEFORE INSERT OR UPDATE OR DELETE ON erp_{table} FOR EACH ROW EXECUTE FUNCTION erp_guard_ledger_row();\n'
SQL+='''CREATE FUNCTION erp_guard_source_record() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE source_state text;
BEGIN
 SELECT state INTO source_state FROM erp_document WHERE id=OLD.source_id;
 IF source_state='posted' THEN RAISE EXCEPTION 'Posted source records are immutable'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $$;
'''
for table in ['exchangerate','foreignexposure']:
    SQL+=f'CREATE TRIGGER source_immutable BEFORE UPDATE OR DELETE ON erp_{table} FOR EACH ROW EXECUTE FUNCTION erp_guard_source_record();\n'

class Migration(migrations.Migration):
    dependencies=[('erp','0010_foreign_monetary_subledgers')]
    operations=[migrations.RunPython(seed,migrations.RunPython.noop),migrations.RunSQL(SQL)]
