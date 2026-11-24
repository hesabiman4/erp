"""Start/open exactly this installed ERP, without resetting data or killing ports."""
import argparse,hashlib,json,os,socket,subprocess,sys,time,urllib.request,webbrowser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def instance_id(root=ROOT):return hashlib.sha256(os.path.normcase(str(Path(root).resolve())).encode('utf-8')).hexdigest()[:24]
def inspect(port,root=ROOT,timeout=3):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health/',timeout=timeout) as response:data=json.load(response)
        if not isinstance(data,dict):return {'state':'unrecognized'}
        if data.get('installation_id')!=instance_id(root):return {'state':'different_installation'}
        return {'state':'ready' if data.get('status')=='ok' and data.get('database')=='postgresql' else 'starting','running_release':data.get('running_release')}
    except Exception:return {'state':'unavailable'}

def occupied(port):
    with socket.socket() as probe:
        probe.settimeout(.5);return probe.connect_ex(('127.0.0.1',port))==0

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',type=int,default=8080);p.add_argument('--timeout',type=int,default=180);p.add_argument('--no-browser',action='store_true');p.add_argument('--status',action='store_true');a=p.parse_args(argv)
    if not 1<=a.port<=65535 or not 1<=a.timeout<=600:p.error('Invalid port or startup timeout.')
    from release_check import check_release
    release=check_release(ROOT);state=inspect(a.port)
    if a.status:print(json.dumps(state));return 0 if state['state']=='ready' else 1
    if release['state']!='verified' or not release.get('dependencies_matched'):raise SystemExit('This installation needs a verified build. Ask the operator to build and review the release; no process or data was changed.')
    if occupied(a.port):
        if state['state']!='ready':raise SystemExit('This port is occupied or still starting and its installation could not be verified. Existing processes were preserved. Inspect local runtime logs.')
        if state.get('running_release')!=release['release_id']:raise SystemExit('The running ERP has a different release. Close its own runtime and start this reviewed installation again. No process was stopped.')
    else:
        logs=ROOT/'.local';logs.mkdir(exist_ok=True)
        with (logs/'launcher.log').open('a',encoding='utf8') as log:
            subprocess.Popen([sys.executable,str(ROOT/'scripts/run_runtime.py'),'--port',str(a.port)],cwd=ROOT,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),close_fds=True)
        deadline=time.monotonic()+a.timeout
        while time.monotonic()<deadline:
            state=inspect(a.port)
            if state['state']=='different_installation':raise SystemExit('Another installation is using the selected port. No process was stopped.')
            if state['state']=='ready':break
            time.sleep(1)
        if state['state']!='ready':raise SystemExit('ERP has not become ready. Review .local/launcher.log and database/runtime logs. No database reset was performed.')
        if state.get('running_release')!=release['release_id']:raise SystemExit('Running release does not match the reviewed build. No browser was opened.')
    url=f'http://127.0.0.1:{a.port}/'
    if not a.no_browser:webbrowser.open(url)
    print(json.dumps({'state':'ready','url':url,'installation_verified':True,'release_matched':True}));return 0
if __name__=='__main__':raise SystemExit(main())
