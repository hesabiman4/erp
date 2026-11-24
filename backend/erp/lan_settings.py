"""Local host-operator LAN configuration, separate from business accounting settings."""
import json
import ssl
import urllib.request
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection
from django.http import HttpResponse
from .api import Boundary,response
from .backup_settings import authorize
from .models import AuditEvent
from . import lan_security as tls


def current():return tls.read_configuration(settings.ROOT_DIR,settings.DATABASES['default']['NAME'])


def running(config):
    try:
        summary=tls.certificate_summary(settings.ROOT_DIR,config)
        context=ssl.create_default_context(cafile=str(tls.material(settings.ROOT_DIR,config)/'ca.crt'))
        # Never use system proxies for a private installation health check.
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
        with opener.open(summary['url']+'api/health/',timeout=2) as source:value=json.load(source)
        from .installation import installation_id,running_release
        return value.get('status')=='ok' and value.get('installation_id')==installation_id() and value.get('running_release')==running_release()
    except Exception:return False


class LANSettingsAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request);authorize(ctx,request);config=current()
        if request.query_params.get('certificate')=='1':
            try:data=(tls.material(settings.ROOT_DIR,config)/'ca.crt').read_bytes()
            except (OSError,ValueError):raise ValidationError('Configure LAN HTTPS first.')
            result=HttpResponse(data,content_type='application/x-x509-ca-cert');result['Content-Disposition']='attachment; filename="nawa-lan-ca.crt"';result['Cache-Control']='no-store';return result
        value={'state':'not_configured','addresses':tls.local_addresses(),'phone_trust_verified':False,'physical_device_verified':False,'running_verified':False}
        if config:
            try:value.update(tls.certificate_summary(settings.ROOT_DIR,config));value.update(state='configured',running_verified=running(config))
            except (OSError,ValueError):value.update(state='needs_renewal')
        return response(value)

    def post(self,request):
        ctx=self.ctx(request);authorize(ctx,request)
        if request.data.get('action')!='configure':raise ValidationError('Choose a supported LAN action.')
        with connection.cursor() as cursor:cursor.execute('SELECT pg_try_advisory_lock(%s)',[817290312]);locked=cursor.fetchone()[0]
        if not locked:raise ValidationError('LAN configuration is busy. Try again shortly.')
        try:
            try:config=tls.configure(settings.ROOT_DIR,settings.DATABASES['default']['NAME'],request.data.get('address'),request.data.get('port',8443))
            except (ValueError,OSError):raise ValidationError('Select an available private LAN address and valid port. Configuration failed; no server was started.')
            AuditEvent.objects.create(business=ctx.business,user=ctx.user,action='lan.configure',target=tls.database_tag(settings.DATABASES['default']['NAME']),details={'address':config['address'],'port':config['port'],'phone_trust_verified':False})
            return response({'configured':True,'server_started':False,**tls.certificate_summary(settings.ROOT_DIR,config)})
        finally:
            with connection.cursor() as cursor:cursor.execute('SELECT pg_advisory_unlock(%s)',[817290312])
