from pathlib import Path
from django.conf import settings
from django.http import FileResponse,HttpResponse

def shell(request,path=''):
    if not settings.SERVE_FRONTEND:return HttpResponse('Use the configured frontend URL.',status=404)
    entry=settings.ROOT_DIR/'frontend'/'dist'/'index.html'
    if not entry.is_file():return HttpResponse('Frontend build is missing. Run npm --prefix frontend run build.',status=503)
    response=FileResponse(entry.open('rb'),content_type='text/html; charset=utf-8')
    response['Cache-Control']='no-cache'
    return response
