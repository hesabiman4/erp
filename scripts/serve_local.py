"""Single-origin built ERP server; defaults to loopback, no public exposure."""
import argparse,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8080);parser.add_argument('--threads',type=int,default=8)
    args=parser.parse_args()
    if not 1<=args.port<=65535 or not 1<=args.threads<=64:parser.error('Invalid port or thread count.')
    if not (ROOT/'frontend/dist/index.html').is_file():raise SystemExit('Build frontend before serving: npm --prefix frontend run build')
    os.environ['ERP_SERVE_FRONTEND']='1'
    os.environ.setdefault('DJANGO_DEBUG','0')
    if args.host in {'127.0.0.1','localhost','::1'}:os.environ.setdefault('ERP_LOCAL_HTTP','1')
    import json
    try:os.environ['ERP_RUNNING_RELEASE']=json.loads((ROOT/'.local/releases/current.json').read_text(encoding='utf8'))['release_id']
    except (OSError,ValueError,KeyError):os.environ.pop('ERP_RUNNING_RELEASE',None)
    from config.wsgi import application
    from whitenoise import WhiteNoise
    from waitress import serve
    wrapped=WhiteNoise(application,root=str(ROOT/'frontend/dist'),prefix='',max_age=3600)
    print(f'ERP single-origin server: http://{args.host}:{args.port}',flush=True)
    serve(wrapped,host=args.host,port=args.port,threads=args.threads,expose_tracebacks=False,channel_timeout=60)
if __name__=='__main__':main()
