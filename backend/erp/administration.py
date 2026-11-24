from django.core.exceptions import ValidationError
from .models import Product, Party

IMPORT_FIELDS={
 'products':['code','name','kind','line','unit','price'],
 'parties':['name','kind','phone','address','notes'],
}

def prepare_import(ctx,resource,rows):
    if resource not in IMPORT_FIELDS: raise ValidationError('Unsupported import resource.')
    if not rows or len(rows)>1000: raise ValidationError('Import between 1 and 1,000 rows.')
    Model=Product if resource=='products' else Party
    prepared=[]; errors=[]; codes=set()
    for index,row in enumerate(rows,2):
        try:
            if set(row)-set(IMPORT_FIELDS[resource]): raise ValidationError('CSV includes unknown columns.')
            data={k:(v or '').strip() for k,v in row.items()}
            if resource=='products':
                if data.get('line') not in ctx.membership.product_lines: raise ValidationError('Product line is outside your assignment.')
                if data.get('code') in codes: raise ValidationError('Duplicate item code in CSV.')
                codes.add(data.get('code'))
            obj=Model(business=ctx.business,**data); obj.full_clean()
            prepared.append(data)
        except ValidationError as exc: errors.append({'row':index,'error':'; '.join(exc.messages)})
    return prepared,errors

def catalog_import(ctx,payload,doc):
    resource=payload['resource']; rows,errors=prepare_import(ctx,resource,payload['rows'])
    if errors: raise ValidationError([f"Row {e['row']}: {e['error']}" for e in errors])
    Model=Product if resource=='products' else Party
    identifiers=[]
    for row in rows:
        obj=Model(business=ctx.business,**row); obj.full_clean(); obj.save(); identifiers.append(obj.pk)
        if resource=='products': ctx.lines.add(obj.line)
    return {'resource':resource,'count':len(identifiers),'ids':identifiers}

OPERATIONS={'catalog_import':('settings.manage',catalog_import)}
