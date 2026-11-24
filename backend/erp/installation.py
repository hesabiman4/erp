"""Public opaque installation identity; no filesystem, user or ledger details."""
import hashlib
import os
from django.conf import settings

def installation_id():
    root=os.path.normcase(str(settings.ROOT_DIR.resolve()))
    return hashlib.sha256(root.encode('utf-8')).hexdigest()[:24]

def running_release():
    value=os.environ.get('ERP_RUNNING_RELEASE','')
    return value if len(value)==64 and all(c in '0123456789abcdef' for c in value) else None
