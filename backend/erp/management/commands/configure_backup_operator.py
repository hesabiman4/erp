from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth import get_user_model
from erp.backup_settings import operators_path,read_json,write_json,tag

class Command(BaseCommand):
    help='Locally grant one existing account host-backup configuration access; grants no business or Django administrator membership.'
    def add_arguments(self,parser):parser.add_argument('--username',required=True)
    def handle(self,*args,**options):
        user=get_user_model().objects.filter(username=options['username'],is_active=True).first()
        if not user:raise CommandError('Select an existing active user.')
        config=read_json(operators_path());databases=config.get('databases',{});ids=set(databases.get(tag(),[]));ids.add(user.pk);databases[tag()]=sorted(ids)
        write_json(operators_path(),{'databases':databases})
        self.stdout.write('Host-backup operator access configured for the selected local account; no business permissions changed.')
