from django.db import migrations,models

def set_requested_default(apps,schema_editor):
    # Owner explicitly requested Jalali as the application's new default.
    # Subsequent individual Gregorian selections continue to persist normally.
    apps.get_model('erp','UserPreference').objects.all().update(calendar='jalali')

class Migration(migrations.Migration):
    dependencies=[('erp','0012_protect_operational_history')]
    operations=[migrations.AlterField(model_name='userpreference',name='calendar',field=models.CharField(max_length=12,default='jalali',choices=[('gregorian','Gregorian'),('jalali','Jalali')])),migrations.RunPython(set_requested_default,migrations.RunPython.noop)]
