"""Explicit alias for host-wide backup and LAN TLS configuration authority."""
from .configure_backup_operator import Command as BackupOperatorCommand

class Command(BackupOperatorCommand):
    help='Locally allow an existing user to configure host backup folders and LAN HTTPS; business permissions are still required.'
