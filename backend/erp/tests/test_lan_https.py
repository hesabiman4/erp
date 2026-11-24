"""Actual TLS sockets plus PostgreSQL operator/tenant/financial invariants."""
import ipaddress,json,ssl,sys,threading,urllib.request
from pathlib import Path
from unittest.mock import patch
import pytest
from django.test import override_settings
from erp import lan_security as tls
from erp.models import Document,Entry,StockMovement
from erp.tests.test_api import environment,client_for
from erp.backup_settings import tag
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
from serve_lan import create_server


@pytest.mark.parametrize('address',['0.0.0.0','127.0.0.1','8.8.8.8','169.254.1.2','::1','example.com','192.168.1.1/24',None])
def test_lan_rejects_non_private_binds(address):
    with pytest.raises(ValueError):tls.lan_address(address)


@pytest.mark.parametrize('port',[0,443,65536,True,'8443.5','８４４３',None])
def test_lan_rejects_invalid_ports(port):
    with pytest.raises(ValueError):tls.lan_port(port)


def test_real_tls_trust_hostname_and_no_plaintext_fallback(tmp_path):
    # Patch interface availability only to generate a private-IP SAN on a loopback test socket.
    with patch.object(tls.socket,'socket'):
        config=tls.configure(tmp_path,'tls-test','192.168.31.2',8443)
    folder=tls.material(tmp_path,config);first=tls.certificate_summary(tmp_path,config)
    def app(env,start):
        start('200 OK',[('Content-Type','application/json')]);return [json.dumps({'scheme':env['wsgi.url_scheme'],'remote':env['REMOTE_ADDR']}).encode()]
    server=create_server('127.0.0.1',0,app,folder/'server.crt',folder/'server.key');server.prepare();port=server.bind_addr[1]
    thread=threading.Thread(target=server.serve,daemon=True);thread.start()
    import socket
    try:
        context=ssl.create_default_context(cafile=str(folder/'ca.crt'))
        with socket.create_connection(('127.0.0.1',port),timeout=5) as raw:
            with context.wrap_socket(raw,server_hostname='192.168.31.2') as secure:
                secure.sendall(b'GET / HTTP/1.1\r\nHost: 192.168.31.2\r\nConnection: close\r\n\r\n');parts=[]
                while data:=secure.recv(65536):parts.append(data)
                result=b''.join(parts);assert b'200 OK' in result and b'"scheme": "https"' in result
        for context,hostname in [(ssl.create_default_context(),'192.168.31.2'),(ssl.create_default_context(cafile=str(folder/'ca.crt')),'192.168.31.3')]:
            with socket.create_connection(('127.0.0.1',port),timeout=5) as raw:
                with pytest.raises(ssl.SSLCertVerificationError):context.wrap_socket(raw,server_hostname=hostname)
        with socket.create_connection(('127.0.0.1',port),timeout=5) as raw:
            raw.sendall(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
            try:assert b'200 OK' not in raw.recv(65536)
            except ConnectionResetError:pass
    finally:server.stop();thread.join(timeout=10)
    with patch.object(tls.socket,'socket'):renewed=tls.configure(tmp_path,'tls-test','192.168.31.3',8444)
    assert tls.certificate_summary(tmp_path,renewed)['ca_sha256']==first['ca_sha256']
    assert tls.read_configuration(tmp_path,'another-db')=={}


def test_lan_settings_are_host_only_audited_and_never_financial(environment,tmp_path):
    user,business,member,*_=environment;c=client_for(user,business)
    with override_settings(ROOT_DIR=tmp_path):
        folder=tmp_path/'.local';folder.mkdir();(folder/'host-operators.json').write_text(json.dumps({'databases':{tag():[user.pk]}}))
        counts=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
        assert c.get('/api/lan-settings/').json()['state']=='not_configured'
        with patch.object(tls.socket,'socket'):
            result=c.post('/api/lan-settings/',{'action':'configure','address':'192.168.31.2','port':8443},content_type='application/json')
        assert result.status_code==200,result.content
        assert result.json()['server_started'] is False and result.json()['phone_trust_verified'] is False
        certificate=c.get('/api/lan-settings/?certificate=1');assert certificate.status_code==200 and b'BEGIN CERTIFICATE' in certificate.content and b'PRIVATE KEY' not in certificate.content
        assert c.get('/api/lan-settings/',REMOTE_ADDR='192.168.31.10',HTTP_X_FORWARDED_FOR='127.0.0.1').status_code==403
        assert c.get('/api/lan-settings/?certificate=1',REMOTE_ADDR='192.168.31.10').status_code==403
        member.permissions=['settings.manage'];member.save();assert c.get('/api/lan-settings/').status_code==403
        assert counts==(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())


@pytest.mark.django_db(transaction=True)
def test_django_login_over_real_tls_uses_secure_cookies_and_checks_csrf(environment,tmp_path):
    from django.core.handlers.wsgi import WSGIHandler
    from http.client import HTTPSConnection
    user,business,*_=environment
    with patch.object(tls.socket,'socket'):config=tls.configure(tmp_path,'django-tls','192.168.31.2',8443)
    folder=tls.material(tmp_path,config)
    with override_settings(ALLOWED_HOSTS=['192.168.31.2'],SESSION_COOKIE_SECURE=True,CSRF_COOKIE_SECURE=True,CSRF_TRUSTED_ORIGINS=['https://192.168.31.2']):
        server=create_server('127.0.0.1',0,WSGIHandler(),folder/'server.crt',folder/'server.key');server.prepare();thread=threading.Thread(target=server.serve,daemon=True);thread.start()
        import socket
        def request(method,path,body=None,headers=None):
            context=ssl.create_default_context(cafile=str(folder/'ca.crt'))
            conn=HTTPSConnection('192.168.31.2',server.bind_addr[1],context=context,timeout=10)
            # Connect to loopback while keeping SAN/SNI/Host verification enabled.
            conn._create_connection=lambda addr,*a,**k:socket.create_connection(('127.0.0.1',server.bind_addr[1]),timeout=10)
            conn.request(method,path,body=body,headers={'Host':'192.168.31.2',**(headers or {})});response=conn.getresponse();result=(response.status,dict(response.getheaders()),response.read());conn.close();return result
        try:
            status,headers,body=request('GET','/api/session/');assert status==200 and 'Secure' in headers['Set-Cookie']
            token=json.loads(body)['csrfToken'];cookie=headers['Set-Cookie'].split(';')[0]
            data=json.dumps({'username':user.username,'password':'Long-synthetic-password83'})
            base={'Content-Type':'application/json','Cookie':cookie,'X-CSRFToken':token}
            assert request('POST','/api/session/',data,{**base,'Origin':'https://untrusted.example'})[0]==403
            status,headers,body=request('POST','/api/session/',data,{**base,'Origin':'https://192.168.31.2'})
            assert status==200 and json.loads(body)['user']['username']==user.username and 'Secure' in headers['Set-Cookie']
        finally:server.stop();thread.join(timeout=10)
