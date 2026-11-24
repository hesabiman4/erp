import django.db.models.deletion
from django.db import migrations,models


class Migration(migrations.Migration):
    dependencies=[('erp','0029_document_capture')]
    operations=[
        migrations.CreateModel(name='WorkspacePreference',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('persona',models.CharField(max_length=20)),('updated_at',models.DateTimeField(auto_now=True)),
            ('business',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.business')),
            ('membership',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,to='erp.membership')),
        ]),
        migrations.CreateModel(name='GuideProgress',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('topic',models.CharField(max_length=40)),('version',models.PositiveSmallIntegerField(default=1)),
            ('completed',models.JSONField(default=list)),('updated_at',models.DateTimeField(auto_now=True)),
            ('business',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.business')),
            ('membership',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='erp.membership')),
        ]),
        migrations.AddConstraint(model_name='guideprogress',constraint=models.UniqueConstraint(fields=('business','membership','topic','version'),name='guide_progress_actor_topic')),
        migrations.AddIndex(model_name='document',index=models.Index(fields=['business','kind','state','-id'],name='document_queue_lookup')),
        migrations.RunSQL('''
CREATE TRIGGER business_scope BEFORE INSERT OR UPDATE ON erp_workspacepreference FOR EACH ROW EXECUTE FUNCTION erp_guard_business();
CREATE TRIGGER business_scope BEFORE INSERT OR UPDATE ON erp_guideprogress FOR EACH ROW EXECUTE FUNCTION erp_guard_business();
CREATE FUNCTION erp_guard_workspace_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.business_id,NEW.membership_id) IS DISTINCT FROM (OLD.business_id,OLD.membership_id) THEN RAISE EXCEPTION 'Workspace learning identity is immutable'; END IF;
 IF TG_TABLE_NAME='erp_guideprogress' AND (to_jsonb(NEW)->'topic',to_jsonb(NEW)->'version') IS DISTINCT FROM (to_jsonb(OLD)->'topic',to_jsonb(OLD)->'version') THEN RAISE EXCEPTION 'Learning version identity is immutable'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER workspace_identity BEFORE UPDATE ON erp_workspacepreference FOR EACH ROW EXECUTE FUNCTION erp_guard_workspace_identity();
CREATE TRIGGER workspace_identity BEFORE UPDATE ON erp_guideprogress FOR EACH ROW EXECUTE FUNCTION erp_guard_workspace_identity();
'''),
    ]
