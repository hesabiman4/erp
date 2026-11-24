"""Supervise the built local server and maintenance ticks; only terminate own children."""
import argparse,json,os,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8080);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    if args.check:
        with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/api/health/',timeout=5) as r:print(r.read().decode())
        return
    logs=ROOT/'.local';logs.mkdir(exist_ok=True)
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    # Refuse a port already used by any other process, including another runtime.
    import socket
    with socket.socket() as probe:
        try:probe.bind((args.host,args.port))
        except OSError:raise SystemExit('Runtime port is already in use. Existing process was not stopped.')
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env.local');load_dotenv(ROOT/'.env')
    # Start only this previously initialized local cluster. Never initialize,
    # reset or stop it, and never manage a remote/system database service.
    local_cluster=os.environ.get('PGHOST','127.0.0.1')=='127.0.0.1' and os.environ.get('PGPORT','55432')=='55432' and (ROOT/'.local/pgdata/PG_VERSION').is_file()
    if local_cluster and os.environ.get('ERP_START_LOCAL_DB','1')=='1':
        # A daemon started by pg_ctl may inherit stdout handles on Windows.
        # Use a file, not a capture pipe that can stay open for the daemon's life.
        with (logs/'runtime-database.log').open('a',encoding='utf-8') as database_log:
            started=subprocess.run([sys.executable,str(ROOT/'scripts/local_db.py'),'start'],cwd=ROOT,stdout=database_log,stderr=subprocess.STDOUT,creationflags=flags,timeout=200)
        if started.returncode:raise SystemExit('Project PostgreSQL could not start; inspect its private local log.')
    handles=[];children=[]
    try:
        log=(logs/'runtime-server.log').open('a',encoding='utf-8');handles.append(log)
        server=subprocess.Popen([sys.executable,str(ROOT/'scripts/serve_local.py'),'--host',args.host,'--port',str(args.port)],cwd=ROOT,stdout=log,stderr=log,creationflags=flags);children.append(server)
        next_tick=0;worker=None
        while True:
            if server.poll() is not None:raise SystemExit('Server stopped; inspect .local/runtime-server.log. A startup service may restart this supervisor.')
            if time.monotonic()>=next_tick and (worker is None or worker.poll() is not None):
                out=(logs/'runtime-maintenance.log').open('a',encoding='utf-8');handles.append(out)
                worker=subprocess.Popen([sys.executable,str(ROOT/'backend/manage.py'),'run_maintenance'],cwd=ROOT,stdout=out,stderr=out,creationflags=flags);children.append(worker);next_tick=time.monotonic()+60
                # Close completed parent log handles; children retain their own descriptors.
                out.close();handles.remove(out)
            children=[child for child in children if child.poll() is None]
            time.sleep(1)
    except KeyboardInterrupt:pass
    finally:
        for child in children:
            if child.poll() is None:
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags,timeout=15)
                else:child.terminate()
        for handle in handles:handle.close()
if __name__=='__main__':main()
