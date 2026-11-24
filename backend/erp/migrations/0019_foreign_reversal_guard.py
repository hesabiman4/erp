from importlib import import_module
from django.db import migrations

# 0015 installs this for fresh databases; repeat it for local databases which
# applied that migration before the foreign reversal sign guard was completed.
SQL=import_module('erp.migrations.0015_foreign_extensions').REVERSAL_SQL

class Migration(migrations.Migration):
    dependencies=[('erp','0018_commissions')]
    operations=[migrations.RunSQL(SQL)]
