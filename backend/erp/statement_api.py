import base64
import io
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.http import FileResponse
from .api import Boundary,response,document_data
from .core import execute
from .models import Location
from .statement_models import StatementImport,StatementMatch,StatementReconciliation
from .statement_imports import authorize,statement_for,parse,eligible_entries,MAX_FILE


def payload(request):
    values=dict(request.data.items());values.pop('file',None)
    upload=request.FILES.get('file')
    if not upload or upload.size>MAX_FILE:raise ValidationError('Choose a CSV or XLSX file no larger than 2 MB.')
    raw=upload.read(MAX_FILE+1)
    if len(raw)>MAX_FILE:raise ValidationError('The statement exceeds 2 MB.')
    return values,raw,upload.name


def summary(statement):
    sealed=StatementReconciliation.objects.filter(statement=statement).first()
    matched=StatementMatch.objects.filter(row__statement=statement,released_by__isnull=True).count()
    return {'id':statement.id,'number':statement.source.number,'source_type':statement.source_type,'institution':statement.institution,'account_reference':statement.account_reference,'bank_instrument':statement.instrument_id,'location':statement.location_id,'location_name':statement.location.name,'currency':statement.currency,'starts':statement.starts,'ends':statement.ends,'opening_balance':statement.opening_balance,'closing_balance':statement.closing_balance,'filename':statement.filename,'sha256':statement.sha256,'rows':statement.rows.count(),'matched':matched,'state':'reconciled' if sealed else 'evidence_only' if statement.source_type=='saraf' else 'review','bank_document':sealed.bank_document_id if sealed else None}


class StatementAPI(Boundary):
    def get(self,request,section):
        ctx=self.ctx(request);authorize(ctx)
        selected=request.query_params.get('location') or request.headers.get('X-Location-ID')
        if selected:authorize(ctx,selected)
        if section=='imports':
            query=StatementImport.objects.filter(business=ctx.business).select_related('source','location').order_by('-id')
            if not ctx.membership.all_locations:query=query.filter(location_id__in=ctx.membership.location_ids)
            if selected:query=query.filter(location_id=selected)
            try:offset=max(0,int(request.query_params.get('offset',0)))
            except ValueError:raise ValidationError('Use integer pagination.')
            return response({'results':[summary(s) for s in query[offset:offset+50]],'count':query.count(),'next_offset':offset+50 if query.count()>offset+50 else None,'basis':'Uploaded source evidence and reviewed matches. No live bank or saraf connection is configured by this feature.'})
        statement=statement_for(ctx,request.query_params['id'])
        if section=='source':return FileResponse(io.BytesIO(bytes(statement.original)),as_attachment=True,filename=statement.filename,content_type='application/octet-stream')
        if section!='detail':raise ValidationError('Unknown statement section.')
        entries=eligible_entries(ctx,statement) if statement.source_type=='bank' else []
        if len(entries)>10000:raise ValidationError('This pilot matching workspace supports at most 10,000 historical BANK entries for the chosen location. Use an accountant-reviewed opening migration or extend paging before scale deployment.')
        used=set(StatementMatch.objects.filter(business=ctx.business,released_by__isnull=True).values_list('entry_id',flat=True))
        records=[]
        for row in statement.rows.all().order_by('position'):
            match=row.matches.filter(released_by__isnull=True).select_related('entry__document').first()
            reviews=[{'outcome':r.outcome,'note':r.note,'number':r.source.number,'date':r.source.date,'actor':r.source.created_by.get_full_name() or r.source.created_by.username,'entry':r.entry_id} for r in row.reviews.select_related('source__created_by').order_by('-id')]
            candidates=[]
            if not match:
                for entry in entries:
                    if entry.id in used or entry.document.date<statement.starts or abs((entry.document.date-row.date).days)>7 or entry.debit-entry.credit!=row.amount:continue
                    reference_match=bool(row.reference and row.reference.casefold() in entry.document.number.casefold())
                    candidates.append({'id':entry.id,'number':entry.document.number,'date':entry.document.date,'amount':entry.debit-entry.credit,'reference_match':reference_match,'days':abs((entry.document.date-row.date).days)})
                candidates.sort(key=lambda r:(not r['reference_match'],r['days'],r['id']))
            records.append({'id':row.id,'position':row.position,'date':row.date,'reference':row.reference,'description':row.description,'amount':row.amount,'state':'matched' if match else 'verified_evidence' if reviews and reviews[0]['outcome']=='verified' else 'unmatched','match':{'entry':match.entry_id,'number':match.entry.document.number} if match else None,'candidates':candidates[:20],'candidate_count':len(candidates),'reviews':reviews})
        return response({'statement':summary(statement),'results':records,'basis':'Candidates have the exact signed amount and a ledger date within seven days, inside this statement period. Suggestions never post or automatically match; ambiguity requires review. Finalization requires every current-period BANK entry and every statement row, plus exact opening/closing balances.'})

    def post(self,request,section):
        ctx=self.ctx(request);ctx.require('finance.statements');authorize(ctx)
        if section not in {'preview','commit'}:raise ValidationError('Use preview or commit for a statement upload.')
        values,raw,filename=payload(request)
        if section=='preview':return response(parse(ctx,values,raw,filename))
        document=execute(ctx,'statement_import',{**values,'filename':filename,'source_content':base64.b64encode(raw).decode('ascii')},request.headers.get('Idempotency-Key'))
        return response({'document':document_data(ctx,document),'result':document.result},201)
