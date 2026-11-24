from django.db import migrations

def seed(apps,schema_editor):
    Account=apps.get_model('erp','Account')
    for business in apps.get_model('erp','Business').objects.all():
        Account.objects.get_or_create(business_id=business.id,code='COMMISSION',defaults={'name':'Sales commissions','category':'expense','number':'63200','statement_group':'selling_expenses','control':False})

SQL='\n'.join(f'CREATE TRIGGER business_scope BEFORE INSERT OR UPDATE ON erp_{name} FOR EACH ROW EXECUTE FUNCTION erp_guard_business();\nCREATE TRIGGER source_immutable BEFORE UPDATE OR DELETE ON erp_{name} FOR EACH ROW EXECUTE FUNCTION erp_guard_source_record();' for name in ['commissionpolicy','commissionearning','latecostbill','latecostallocation'])
class Migration(migrations.Migration):
    dependencies=[('erp','0020_late_cost')]
    operations=[migrations.RunPython(seed,migrations.RunPython.noop),migrations.RunSQL(SQL)]
