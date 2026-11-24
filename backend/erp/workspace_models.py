from django.db import models
from .models import Owned


class WorkspacePreference(Owned):
    membership = models.OneToOneField('erp.Membership',on_delete=models.PROTECT)
    persona = models.CharField(max_length=20)
    updated_at = models.DateTimeField(auto_now=True)


class GuideProgress(Owned):
    membership = models.ForeignKey('erp.Membership',on_delete=models.PROTECT)
    topic = models.CharField(max_length=40)
    version = models.PositiveSmallIntegerField(default=1)
    completed = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['business','membership','topic','version'],name='guide_progress_actor_topic')]
