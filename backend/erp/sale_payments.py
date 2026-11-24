"""Reviewed AFN tender lines for a single atomic sale."""
from django.core.exceptions import ValidationError
from .core import D,money,ZERO
from .money_instruments import instrument_for

def sale_payments(ctx,payload,location):
    raw=payload.get('payments')
    if raw is None:
        value=money(payload.get('paid','0'))
        if value<0:raise ValidationError('Payment cannot be negative.')
        kind=payload.get('cash_account','CASH')
        if kind not in ('CASH','BANK'):raise ValidationError('Choose CASH or BANK for the payment.')
        return ([{'amount':str(value),'account':kind,'instrument':payload.get('cash_instrument' if kind=='CASH' else 'bank_instrument'),'reference':str(payload.get('payment_reference',''))[:160]}] if value else []),value
    if not isinstance(raw,list) or len(raw)>10:raise ValidationError('Enter no more than 10 sale payment lines.')
    result=[];total=ZERO
    for row in raw:
        if not isinstance(row,dict) or set(row)-{'amount','account','instrument','reference'}:raise ValidationError('Select valid sale payment fields.')
        amount=D(row.get('amount','0'));kind=row.get('account')
        if amount<=0 or money(amount)!=amount:raise ValidationError('Payment lines must be positive currency amounts with at most two decimals.')
        if kind not in ('CASH','BANK'):raise ValidationError('Choose CASH or BANK for the payment.')
        ident=row.get('instrument');item=instrument_for(ctx,ident,kind,location) if ident else None
        if not isinstance(row.get('reference',''),str) or len(row.get('reference',''))>160:raise ValidationError('Payment reference is too long.')
        result.append({'amount':str(money(amount)),'account':kind,'instrument':item.pk if item else None,'reference':row.get('reference','')});total+=amount
    if 'paid' in payload and money(payload['paid'])!=total:raise ValidationError('Payment lines must equal the received amount.')
    return result,money(total)
