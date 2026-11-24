from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import FileResponse
from .api import Boundary

class AccountingGuideAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request);ctx.require('accounting.view')
        # Fixed allowlist: never use a user-provided filename or arbitrary path.
        language=request.query_params.get('language','fa-AF')
        editions={
            'ps-AF':('Nawa_Beginner_Accounting_Manual_Pashto.pdf','Nawa-Accounting-Manual-Pashto.pdf'),
            'fa-AF':('Nawa_Beginner_Accounting_Manual_Dari.pdf','Nawa-Accounting-Manual-Dari.pdf'),
            'en':('Nawa_Beginner_Accounting_Manual.pdf','Nawa-Accounting-Manual-English.pdf'),
        }
        if language not in editions:
            raise ValidationError('Choose fa-AF (Dari), ps-AF (Pashto) or en (English).')
        source,filename=editions[language]
        result=FileResponse((settings.ROOT_DIR/'output/pdf'/source).open('rb'),as_attachment=True,filename=filename,content_type='application/pdf')
        result['Content-Language']=language
        return result
