"""Explicit private LAN HTTPS service; no proxy headers or HTTP fallback."""
import json,os,ssl,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))


def create_server(address,port,application,certificate,key):
    from cheroot.wsgi import Server
    from cheroot.ssl.builtin import BuiltinSSLAdapter
    from cheroot import errors
    class TLSOnlyAdapter(BuiltinSSLAdapter):
        def wrap(self,sock):
            try:return super().wrap(sock)
            except errors.NoSSLError as error:
                # Reject plaintext at the transport boundary. Cheroot11.1.2's
                # attempted HTTP error response can flush an already closed
                # socket on Windows; no HTTP response is needed on this port.
                raise errors.FatalSSLAlert('Plain HTTP is not accepted on the TLS service.') from error
    server=Server((address,port),application,numthreads=8,max=32,timeout=30,request_queue_size=32)
    server.max_request_body_size=13*1024*1024;server.max_request_header_size=65536
    server.ssl_adapter=TLSOnlyAdapter(str(certificate),str(key))
    server.ssl_adapter.context.minimum_version=ssl.TLSVersion.TLSv1_2
    return server


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env.local');load_dotenv(ROOT/'.env')
    from erp import lan_security as tls
    config=tls.read_configuration(ROOT,os.environ.get('PGDATABASE','sponge_erp'));info=tls.certificate_summary(ROOT,config)
    from release_check import check_release
    release=check_release(ROOT)
    if release['state']!='verified' or not release.get('dependencies_matched'):raise SystemExit('A verified build and matching dependencies are required.')
    os.environ.update(ERP_SERVE_FRONTEND='1',DJANGO_DEBUG='0',ERP_LOCAL_HTTP='0',DJANGO_ALLOWED_HOSTS=info['address'],CSRF_TRUSTED_ORIGINS=info['url'].rstrip('/'),ERP_RUNNING_RELEASE=release['release_id'])
    from config.wsgi import application
    from whitenoise import WhiteNoise
    app=WhiteNoise(application,root=str(ROOT/'frontend/dist'),prefix='',max_age=3600)
    folder=tls.material(ROOT,config)
    server=create_server(info['address'],info['port'],app,folder/'server.crt',folder/'server.key')
    print(json.dumps({'url':info['url'],'ca_sha256':info['ca_sha256'],'phone_trust_verified':False}),flush=True)
    try:server.start()
    finally:server.stop()


if __name__=='__main__':main()
