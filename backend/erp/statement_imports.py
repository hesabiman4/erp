"""Reviewed statement evidence. Imports and matches never manufacture ledger entries."""
import base64
import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum
from .core import Context, D, money, ZERO, get_obj, execute, json_value
from .models import Document, Entry, Account, Product, Location
from .statement_models import StatementImport, StatementRow, StatementReview, StatementMatch, StatementReconciliation

MAX_FILE = 2 * 1024 * 1024
MAX_ROWS = 1000
FIELDS = ('date','reference','description','amount','debit','credit')
ALIASES = {'date':('date','transaction date','تاریخ'), 'reference':('reference','transaction id','ref','مرجع','شماره سند'),
           'description':('description','details','memo','شرح','توضیحات'), 'amount':('amount','signed amount','مبلغ'),
           'debit':('debit','withdrawal','برداشت'), 'credit':('credit','deposit','واریز')}


def fail(message):
    raise ValidationError(message)


def authorize(ctx, location=None):
    ctx.require('finance.view'); ctx.require('payroll.view')
    if not ctx.has('documents.all_lines') and Product.objects.filter(business=ctx.business).exclude(line__in=ctx.membership.product_lines).exists():
        raise PermissionDenied('External statements may contain all product lines and payroll. Complete product-line and payroll scope is required.')
    return get_obj(ctx,Location,location) if location else None


def statement_for(ctx, ident):
    item=get_obj(ctx,StatementImport,ident);authorize(ctx,item.location_id)
    return item


def normalized(value):
    return re.sub(r'\s+',' ',str(value).strip()).casefold()


def exact_money(value, name):
    value=D(value)
    if value!=money(value):fail(f'{name} supports two decimal places; statements are not silently rounded.')
    return value


def xlsx_table(content):
    """Read a bounded first worksheet, never execute formulas or resolve links."""
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members=archive.infolist(); names={item.filename for item in members}
            if len(members)>200 or sum(item.file_size for item in members)>12*1024*1024 or any(item.file_size>6*1024*1024 or item.flag_bits&1 for item in members):fail('The XLSX archive is encrypted or exceeds safe expansion limits.')
            if any('externallink' in name.lower() or name.lower().endswith(('.bin','.vba')) for name in names):fail('Macros and external workbook links are not accepted.')
            def xml(name):
                raw=archive.read(name)
                if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():fail('XML entities are not accepted in workbook files.')
                return ET.fromstring(raw)
            shared=[]
            if 'xl/sharedStrings.xml' in names:
                for item in xml('xl/sharedStrings.xml').findall('s:si',ns):shared.append(''.join(t.text or '' for t in item.findall('.//s:t',ns)))
            workbook=xml('xl/workbook.xml');sheets=workbook.findall('s:sheets/s:sheet',ns)
            if len(sheets)!=1:fail('Use a workbook containing exactly one statement worksheet.')
            rel_id=sheets[0].get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
            rels=xml('xl/_rels/workbook.xml.rels')
            selected=next((x for x in rels if x.get('Id')==rel_id),None)
            if selected is None or selected.get('TargetMode')=='External':fail('The workbook worksheet reference is invalid.')
            target=selected.get('Target','').replace('\\','/')
            if '..' in PurePosixPath(target).parts:fail('Invalid worksheet path.')
            path=target.lstrip('/') if target.startswith('/') else 'xl/'+target
            result=[]
            for row in xml(path).findall('s:sheetData/s:row',ns):
                values={}
                for cell in row.findall('s:c',ns):
                    if cell.find('s:f',ns) is not None:fail('Formula cells are not accepted. Export calculated values before importing.')
                    reference=re.fullmatch(r'([A-Z]+)[0-9]+',cell.get('r',''))
                    if not reference:fail('Invalid cell reference.')
                    column=0
                    for char in reference.group(1):
                        column=column*26+ord(char)-64
                        if column>60:fail('Statement workbooks support at most 60 columns.')
                    if column>60:fail('Statement workbooks support at most 60 columns.')
                    value=cell.findtext('s:v',default='',namespaces=ns);kind=cell.get('t','')
                    if kind=='s':value=shared[int(value)]
                    elif kind=='inlineStr':value=''.join(t.text or '' for t in cell.findall('.//s:t',ns))
                    elif kind in {'e','b'}:fail('Error and boolean cells are not valid statement values.')
                    values[column-1]=value
                if values:result.append([values.get(index,'') for index in range(max(values)+1)])
                if len(result)>MAX_ROWS+1:fail('Import at most 1,000 transaction rows at a time.')
            date1904=workbook.find('s:workbookPr',ns)
            return result,bool(date1904 is not None and date1904.get('date1904') in {'1','true'})
    except (zipfile.BadZipFile,ET.ParseError,KeyError,ValueError,IndexError,OverflowError):
        fail('Invalid XLSX workbook. Export one values-only worksheet with a header row.')


def read_table(content,filename):
    suffix=PurePosixPath(filename.replace('\\','/')).suffix.lower()
    if not content or len(content)>MAX_FILE:fail('Select a statement file between one byte and 2 MB.')
    if suffix=='.xlsx':return (*xlsx_table(content),True)
    if suffix!='.csv':fail('Use CSV or a values-only XLSX workbook. Legacy XLS and macro workbooks are unsupported.')
    try:text=content.decode('utf-16' if content.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
    except UnicodeError:fail('CSV files must use UTF-8 or BOM-marked UTF-16 encoding.')
    if '\x00' in text:fail('CSV content contains null bytes.')
    try:delimiter=csv.Sniffer().sniff(text[:8192],delimiters=',;\t').delimiter
    except csv.Error:delimiter=','
    rows=[]
    try:
        for row in csv.reader(io.StringIO(text),delimiter=delimiter,strict=True):
            rows.append(row)
            if len(row)>60:fail('Statement files support at most 60 columns.')
            if len(rows)>MAX_ROWS+1:fail('Import at most 1,000 transaction rows at a time.')
    except csv.Error:fail('Invalid CSV quoting or an oversized field. Export a plain statement table.')
    return rows,False,False


def day(value,calendar='gregorian',format='iso',excel=False,date1904=False):
    raw=str(value).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789')).strip()
    if excel and re.fullmatch(r'\d+(?:\.0+)?',raw):
        serial=D(raw)
        if serial!=serial.to_integral_value() or serial==60 and not date1904:fail('Invalid Excel statement date.')
        try:result=(date(1904,1,1) if date1904 else date(1899,12,30) if serial>59 else date(1899,12,31))+timedelta(days=int(serial))
        except (OverflowError,ValueError):fail('Invalid Excel statement date.')
    else:
        parts=re.split(r'[-/]',raw)
        if len(parts)!=3 or not all(x.isdigit() for x in parts):fail('Use an unambiguous numeric transaction date and the selected date format.')
        nums=list(map(int,parts))
        if format=='dmy':nums=[nums[2],nums[1],nums[0]]
        elif format=='mdy':nums=[nums[2],nums[0],nums[1]]
        elif format!='iso':fail('Choose ISO, day/month/year or month/day/year.')
        try:
            if calendar=='jalali':
                import jdatetime
                result=jdatetime.date(*nums).togregorian()
            elif calendar=='gregorian':result=date(*nums)
            else:fail('Choose Jalali or Gregorian statement dates.')
        except (ValueError,TypeError,OverflowError):fail('Invalid transaction date in the selected calendar.')
    if not 1900<=result.year<=2199:fail('Transaction dates must be within supported years 1900-2199.')
    return result


def metadata(ctx,p):
    location=authorize(ctx,p['location']);kind=p.get('source_type','bank')
    if kind not in {'bank','saraf'}:fail('Choose bank or saraf evidence.')
    institution=str(p.get('institution','')).strip();reference=str(p.get('account_reference','')).strip()
    if not institution or len(institution)>150 or not reference or len(reference)>100:fail('Provide the institution and a specific account reference within their field limits.')
    currency=str(p.get('currency','AFN')).upper()
    if currency!='AFN':fail('This import release supports AFN statement quantities only; foreign statements require a separate reconciled monetary matching workflow.')
    start=day(p['starts']);end=day(p['ends'])
    if start>end:fail('Statement start cannot follow its end.')
    opening=exact_money(p.get('opening_balance','0'),'Opening balance');closing=exact_money(p['closing_balance'],'Closing balance')
    account=None;instrument=None
    if kind=='bank':
        account=Account.objects.filter(business=ctx.business,code='BANK').first()
        if not account:fail('Configure the BANK control account first.')
        from .money_instruments import resolve
        from types import SimpleNamespace
        instrument=resolve(ctx,SimpleNamespace(data=p,kind='statement_import'),'BANK',location)
        if instrument and instrument.institution and (normalized(instrument.institution),normalized(instrument.account_reference))!=(normalized(institution),normalized(reference)):fail('Statement institution/account reference must match the selected bank instrument.')
        bound_query=StatementImport.objects.filter(business=ctx.business,location=location,source_type='bank')
        if instrument:
            from django.db.models import Q
            bound_query=bound_query.filter(Q(instrument=instrument)|(Q(instrument__isnull=True) if instrument.legacy else Q(pk__in=[])))
        else:bound_query=bound_query.filter(instrument__isnull=True)
        bound=bound_query.order_by('id').first()
        if bound and (normalized(bound.institution),normalized(bound.account_reference))!=(normalized(institution),normalized(reference)):
            fail('This location BANK pool is already bound to another institution/account reference. Choose the corresponding separately registered bank instrument; account identities cannot be mixed.')
    return {'location':location,'source_type':kind,'institution':institution,'account_reference':reference,'currency':currency,'starts':start,'ends':end,'opening_balance':opening,'closing_balance':closing,'account':account,'instrument':instrument}


def parse(ctx,p,content,filename):
    meta=metadata(ctx,p);table,date1904,excel=read_table(content,filename)
    if not table or not any(any(str(c).strip() for c in row) for row in table[1:]):fail('The statement needs a header row and at least one transaction.')
    headers=[str(x).strip() for x in table[0]]
    if len(headers)>60 or len(set(normalized(x) for x in headers))!=len(headers):fail('Use no more than 60 uniquely named header columns.')
    mapping=p.get('mapping') or {}
    if isinstance(mapping,str):
        try:mapping=json.loads(mapping)
        except ValueError:fail('Invalid column mapping.')
    if not isinstance(mapping,dict) or set(mapping)-set(FIELDS):fail('Use the supported statement mapping fields.')
    resolved={}
    for field in FIELDS:
        name=mapping.get(field)
        if field in mapping and not name:continue
        if name and name not in headers:fail('A selected column is not present in the uploaded file.')
        if name:resolved[field]=headers.index(name)
        else:
            found=[index for index,h in enumerate(headers) if normalized(h) in ALIASES[field]]
            if found:resolved[field]=found[0]
    if 'date' not in resolved or 'description' not in resolved or not ('amount' in resolved or {'debit','credit'}<=set(resolved)):
        return {'headers':headers,'needs_mapping':True,'mapping':{key:headers[index] for key,index in resolved.items()},'rows':[],'metadata':json_value(meta),'valid':False}
    fingerprints=set();rows=[]
    for position,values in enumerate(table[1:],2):
        if not any(str(value).strip() for value in values):continue
        if len(values)>len(headers):fail(f'Row {position}: values extend beyond the statement header. Check the CSV delimiter and quoting.')
        def cell(field):return str(values[resolved[field]]).strip() if field in resolved and resolved[field]<len(values) else ''
        when=day(cell('date'),p.get('date_calendar','gregorian'),p.get('date_format','iso'),excel,date1904)
        if not meta['starts']<=when<=meta['ends']:fail(f'Row {position}: transaction date is outside this statement window.')
        if 'amount' in resolved:amount=exact_money(cell('amount'),'Transaction amount')
        else:
            debit=exact_money(cell('debit') or '0','Debit');credit=exact_money(cell('credit') or '0','Credit')
            if debit<0 or credit<0 or debit and credit:fail(f'Row {position}: use one nonnegative debit or credit side.')
            amount=credit-debit # Bank perspective: deposits positive, withdrawals negative.
        if not amount:fail(f'Row {position}: zero-value transactions are not accepted.')
        description=cell('description');reference=cell('reference')
        if not description or len(description)>1000 or len(reference)>150:fail(f'Row {position}: description is required (maximum 1,000 characters), reference maximum 150.')
        key=[meta['location'].id,meta['source_type'],normalized(meta['institution']),normalized(meta['account_reference']),str(when),str(money(amount)),normalized(reference),normalized(description)]
        fingerprint=hashlib.sha256(json.dumps(key,ensure_ascii=False).encode()).hexdigest()
        if fingerprint in fingerprints:fail(f'Row {position}: duplicate transaction. Supply the real distinct transaction reference when identical transactions are legitimate.')
        fingerprints.add(fingerprint);rows.append({'position':position,'date':when,'reference':reference,'description':description,'amount':amount,'fingerprint':fingerprint})
    if money(meta['opening_balance']+sum((row['amount'] for row in rows),ZERO))!=meta['closing_balance']:fail('Opening balance plus every signed transaction must equal the stated closing balance. Do not omit fees or unresolved transactions.')
    duplicates=list(StatementRow.objects.filter(business=ctx.business,fingerprint__in=fingerprints).values_list('position',flat=True))
    return {'headers':headers,'needs_mapping':False,'mapping':{key:headers[index] for key,index in resolved.items()},'rows':rows,'metadata':json_value(meta),'valid':not duplicates,'duplicates':len(duplicates),'file_sha256':hashlib.sha256(content).hexdigest(),'basis':'Deposits positive, withdrawals negative. Import records evidence only; human review is required. Saraf records are AFN evidence only, without a claimed saraf ledger reconciliation.'}


def import_statement(ctx,p,doc):
    try:content=base64.b64decode(p['source_content'],validate=True)
    except (ValueError,TypeError):fail('Invalid source file encoding.')
    filename=str(p.get('filename','')).replace('\\','/').split('/')[-1]
    if not filename or len(filename)>200:fail('Choose a valid statement filename.')
    parsed=parse(ctx,p,content,filename)
    if not parsed['valid']:fail('Resolve missing mappings or previously imported transactions before committing.')
    meta=metadata(ctx,p)
    if meta['ends']>doc.date:fail('A statement cannot finish after its recording date.')
    statement=StatementImport.objects.create(business=ctx.business,**meta,filename=filename,sha256=parsed['file_sha256'],original=content,source=doc)
    StatementRow.objects.bulk_create([StatementRow(business=ctx.business,statement=statement,**row) for row in parsed['rows']])
    # Original bytes are private in the immutable evidence record, never echoed
    # through generic document JSON/print; idempotency hashes retain the request.
    doc.data={key:value for key,value in doc.data.items() if key!='source_content'}
    doc.location=meta['location']
    return {'statement':statement.id,'rows':len(parsed['rows']),'source_type':statement.source_type,'filename':filename,'sha256':statement.sha256,'opening_balance':statement.opening_balance,'closing_balance':statement.closing_balance,'financial_posting':False}


def eligible_entries(ctx,statement):
    from .api import doc_permission
    query=Entry.objects.filter(document__business=ctx.business,document__state='posted',location=statement.location,account=statement.account,document__date__lte=statement.ends).select_related('document','account')
    from .money_instruments import legacy_for,entries_for
    instrument=statement.instrument or legacy_for(ctx,statement.location_id,'BANK')
    if instrument:query=query.filter(pk__in=entries_for(instrument).values('pk'))
    result=[]
    for entry in query.order_by('document__date','pk'):
        # Do not silently omit inaccessible financial rows and call the remainder
        # a complete bank statement. The caller must have complete source access.
        doc_permission(ctx,entry.document);result.append(entry)
    return result


def review_statement(ctx,p,doc):
    row=get_obj(ctx,StatementRow,p['row']);statement=statement_for(ctx,row.statement_id)
    if StatementReconciliation.objects.filter(statement=statement).exists():fail('This statement is finalized; its reviewed matching history is sealed.')
    if doc.date<statement.source.date:fail('A review cannot precede import.')
    note=str(p.get('note','')).strip();outcome=p.get('outcome')
    if not note or len(note)>2000:fail('Record the review reason or matching evidence (maximum 2,000 characters).')
    active=StatementMatch.objects.filter(row=row,released_by__isnull=True).first();entry=None
    if outcome=='match':
        if statement.source_type!='bank':fail('Saraf evidence cannot be matched to the BANK ledger. Record a verified evidence review instead.')
        if active:fail('Unmatch the current allocation with a reason before selecting another entry.')
        valid={entry.id:entry for entry in eligible_entries(ctx,statement)};entry=valid.get(int(p.get('entry',0)))
        if not entry or entry.document.date<statement.starts or abs((entry.document.date-row.date).days)>7 or entry.debit-entry.credit!=row.amount:fail('Choose a posted BANK entry at this location, within this period and seven days of the bank date, with the exact signed amount.')
        if StatementMatch.objects.filter(business=ctx.business,entry=entry,released_by__isnull=True).exists():fail('This ledger entry is already matched to a statement transaction.')
        StatementMatch.objects.create(business=ctx.business,row=row,entry=entry,source=doc)
    elif outcome=='unmatch':
        if not active:fail('This row has no active match.')
        entry=active.entry;active.released_by=doc;active.save(update_fields=['released_by'])
    elif outcome=='unmatched':
        if active:fail('Release the current match before recording an unresolved difference.')
    elif outcome=='verified':
        if statement.source_type!='saraf':fail('Bank transactions require an exact ledger match; evidence verification alone does not reconcile them.')
    else:fail('Choose match, unmatch, unmatched or saraf verified evidence.')
    review=StatementReview.objects.create(business=ctx.business,row=row,outcome=outcome,entry=entry,note=note,source=doc)
    doc.reference=statement.source;doc.location=statement.location
    return {'statement':statement.id,'row':row.id,'review':review.id,'outcome':outcome,'entry':entry.id if entry else None,'note':note,'financial_posting':False}


def reconcile_statement(ctx,p,doc):
    ctx.require('finance.post');statement=statement_for(ctx,p['statement'])
    if statement.source_type!='bank':fail('Saraf imports are evidence-only; no BANK reconciliation or saraf liability is created.')
    if statement.closing_balance<0:fail('Negative/overdrawn statements can be retained and reviewed as evidence, but the existing BANK reconciliation document does not support a negative closing amount.')
    if StatementReconciliation.objects.filter(statement=statement).exists():fail('This statement is already finalized.')
    rows=list(statement.rows.all());matches=list(StatementMatch.objects.filter(business=ctx.business,row__statement=statement,released_by__isnull=True).select_related('entry'))
    if len(rows)!=len(matches):fail('Match every statement transaction before finalization. Record missing fees/payments through their original authorized workflows.')
    entries=eligible_entries(ctx,statement)
    opening=sum((entry.debit-entry.credit for entry in entries if entry.document.date<statement.starts),ZERO)
    if opening!=statement.opening_balance:fail('The statement opening balance does not match the BANK ledger before this period. Review earlier transactions first.')
    current={entry.id for entry in entries if entry.document.date>=statement.starts}
    if current!={match.entry_id for match in matches}:fail('Every posted BANK entry in this period must match exactly one statement row. Unmatched timing differences remain unresolved.')
    from .money_instruments import legacy_for
    selected=statement.instrument or legacy_for(ctx,statement.location_id,'BANK')
    result=execute(ctx,'bank_reconcile',{'date':str(doc.date),'account':'BANK','location':statement.location_id,'through_date':str(statement.ends),'statement_balance':str(statement.closing_balance),'entry_ids':[entry.id for entry in entries],**({'bank_instrument':selected.pk} if selected else {})},f'statement-reconcile-{statement.id}-{doc.id}')
    StatementReconciliation.objects.create(business=ctx.business,statement=statement,bank_document=result,source=doc)
    doc.reference=statement.source;doc.location=statement.location
    return {'statement':statement.id,'bank_document':result.id,'closing_balance':statement.closing_balance,'financial_posting':False,'basis':'Reviewed imported evidence invokes the existing exact BANK reconciliation; no journal or cash movement is created.'}


def document_guard(ctx,doc):
    if doc.kind.startswith('statement_'):
        authorize(ctx,doc.location_id or doc.data.get('location'))
        ident=doc.result.get('statement')
        if ident:statement_for(ctx,ident)


OPERATIONS={'statement_import':('finance.statements',import_statement),'statement_review':('finance.statements',review_statement),'statement_reconcile':('finance.statements',reconcile_statement)}
