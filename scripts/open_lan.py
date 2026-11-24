"""Start or verify this installation's explicitly configured private HTTPS service."""
import json,os,ssl,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))


def inspect(info,folder):
    context=ssl.create_default_context(cafile=str(folder/'ca.crt'))
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
    with opener.open(info['url']+'api/health/',timeout=2) as response:return json.load(response)


def main():
    from dotenv import load_dotenv
    from erp import lan_security as tls
    from release_check import check_release
    from open_erp import instance_id
    load_dotenv(ROOT/'.env.local');load_dotenv(ROOT/'.env')
    config=tls.read_configuration(ROOT,os.environ.get('PGDATABASE','sponge_erp'));info=tls.certificate_summary(ROOT,config);folder=tls.material(ROOT,config)
    release=check_release(ROOT)
    if release['state']!='verified' or not release.get('dependencies_matched'):raise SystemExit('Build and review the ERP release first.')
    import socket
    with socket.socket() as probe:
        probe.settimeout(1);occupied=probe.connect_ex((info['address'],info['port']))==0
    if not occupied:
        with (ROOT/'.local/lan-server.log').open('a',encoding='utf8') as log:
            subprocess.Popen([sys.executable,str(ROOT/'scripts/serve_lan.py')],cwd=ROOT,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),close_fds=True)
    for attempt in range(30):
        try:
            value=inspect(info,folder)
            if value.get('installation_id')!=instance_id(ROOT) or value.get('running_release')!=release['release_id']:raise SystemExit('A different installation or release occupies this port. Existing processes were preserved.')
            if value.get('status')=='ok':print(json.dumps({'state':'ready','url':info['url'],'phone_trust_verified':False}));return
        except (OSError,ValueError):
            if occupied:raise SystemExit('The occupied port could not be verified. Existing processes were preserved.')
        time.sleep(1)
    raise SystemExit('HTTPS did not become ready. Review .local/lan-server.log; no success was reported.')


if __name__=='__main__':main()
