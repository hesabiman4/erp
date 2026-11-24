from importlib import import_module
from django.db import migrations

class Migration(migrations.Migration):
    dependencies=[('erp','0021_commission_guards')]
    operations=[migrations.RunSQL(import_module('erp.migrations.0015_foreign_extensions').REVERSAL_SQL)]
