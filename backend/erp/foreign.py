"""AFN-functional monetary tracking, settlement, revaluation and internal remittances.

Invoice registration tags an already-posted, wholly unpaid AFN invoice at its
original date and exact contractual rate. It never invents additional revenue.
"""
from decimal import Decimal
from django.core.exceptions import ValidationError,PermissionDenied
from django.db.models import Sum,Max
from .models import (ExchangeRate,ForeignExposure,ForeignMovement,ForeignWallet,ForeignWalletMovement,
 Remittance,RemittanceAdjustment,Document,Location,Allocation)
from .core import D,money,get_obj,journal
from .growth import positive,nonnegative,text

ZERO=Decimal('0')
CASH_CODES={'FX_CASH','FX_BANK','FX_TRANSIT'}
def fail(message):raise ValidationError(message)
def currency(ctx,value):
    if ctx.business.currency!='AFN':fail('Foreign monetary tracking currently requires functional AFN.')
    if value not in {'USD','PKR'}:fail('Select USD or PKR; rates mean AFN per one foreign currency unit.')
    return value
def amount(value):
    value=positive(value)
    if value!=money(value):fail('Foreign amounts support two decimal places.')
    return value
def rate_value(value):
    value=positive(value)
    if value!=value.quantize(Decimal('.00000001')):fail('Exchange rates support eight decimal places.')
    return value
def exchange_rate(ctx,p,doc,code):
    if p.get('rate_record'):
        rate=get_obj(ctx,ExchangeRate,p['rate_record'])
        if rate.currency!=code or rate.date>doc.date:fail('Select a rate for this currency on or before the event date.')
        return rate.rate
    ctx.require('finance.fx_rate')
    if not str(p.get('rate_reference','')).strip():fail('An entered rate requires its source/reference.')
    return rate_value(p['rate'])
def chronological(query,date,source_date=None):
    latest=query.aggregate(d=Max('document__date'))['d']
    if (latest and date<latest) or (source_date and date<source_date):fail('Foreign subledger events must follow their source and latest movement date.')
def exposure_balance(item,through=None):
    query=item.movements.filter(document__state='posted')
    if through:query=query.filter(document__date__lte=through)
    sums=query.aggregate(q=Sum('quantity'),v=Sum('base_value'))
    return item.foreign_amount+(sums['q'] or ZERO),money(item.invoice.amount+(sums['v'] or ZERO))
def wallet_balance(wallet):
    sums=wallet.movements.filter(document__state='posted').aggregate(q=Sum('quantity'),v=Sum('base_value'))
    return sums['q'] or ZERO,money(sums['v'] or ZERO)
def wallet_code(wallet):return 'FX_BANK' if wallet.kind=='bank' else 'FX_CASH'
def wallet_release(ctx,wallet,qty,doc):
    chronological(wallet.movements,doc.date,wallet.source.date)
    available,value=wallet_balance(wallet)
    if qty>available:fail('Insufficient foreign currency in the selected wallet.')
    released=value if qty==available else money(value*qty/available)
    ForeignWalletMovement.objects.create(business=ctx.business,wallet=wallet,document=doc,quantity=-qty,base_value=-released)
    return released
def wallet_in(ctx,wallet,qty,value,doc):
    chronological(wallet.movements,doc.date,wallet.source.date)
    ForeignWalletMovement.objects.create(business=ctx.business,wallet=wallet,document=doc,quantity=qty,base_value=value)
def signed(account,value,location,party=None):
    return {'account':account,'debit' if value>=0 else 'credit':abs(value),'location':location,**({'party':party} if party else {})}
def difference(value,location):
    # A debit imbalance is a gain; a credit imbalance is a loss.
    return signed('FX_GAIN' if value>=0 else 'FX_LOSS',-value,location)

def record_rate(ctx,p,doc):
    code=currency(ctx,p['foreign_currency']);item=ExchangeRate.objects.create(business=ctx.business,currency=code,date=doc.date,rate=rate_value(p['rate']),reference=text(p,'reference',250),source=doc)
    return {'rate_record':item.id,'rate':str(item.rate),'unit':f'AFN per 1 {code}','financial_posting':False}

def wallet_create(ctx,p,doc):
    location=get_obj(ctx,Location,p['location']);kind=p.get('kind','cash');code=currency(ctx,p['foreign_currency'])
    if kind not in {'cash','bank'}:fail('Wallet kind must be cash or bank.')
    wallet=ForeignWallet.objects.create(business=ctx.business,name=text(p,'name',150),location=location,currency=code,kind=kind,source=doc)
    doc.location=location;return {'wallet':wallet.id,'currency':code,'balance':'0.00'}

def wallet_opening(ctx,p,doc):
    ctx.require('accounting.opening');wallet=get_obj(ctx,ForeignWallet,p['wallet'])
    if wallet.movements.exists():fail('Opening balance must be the first wallet movement.')
    qty=amount(p['foreign_amount']);rate=exchange_rate(ctx,p,doc,wallet.currency);value=money(qty*rate)
    text(p,'reason');wallet_in(ctx,wallet,qty,value,doc)
    journal(ctx,doc,[signed(wallet_code(wallet),value,wallet.location_id),signed('EQUITY',-value,wallet.location_id)])
    doc.location=wallet.location;doc.amount=value
    return {'wallet':wallet.id,'foreign_amount':str(qty),'functional_amount':str(value),'rate':str(rate)}

def register_exposure(ctx,p,doc):
    bill=get_obj(ctx,Document,p['invoice']);code=currency(ctx,p['foreign_currency']);qty=amount(p['foreign_amount']);rate=exchange_rate(ctx,p,doc,code)
    if bill.kind not in {'sale','purchase_bill','opening_receivable','opening_payable'} or bill.state!='posted' or not bill.party_id:fail('Select a posted customer/supplier invoice with an identifiable party.')
    ctx.require('sales.view' if bill.kind in {'sale','opening_receivable'} else 'purchases.view')
    if doc.date!=bill.date:fail('Register foreign terms at the original invoice date, in an open period.')
    if Allocation.objects.filter(invoice=bill).exists() or bill.children.filter(kind__in=['sales_return','purchase_return','receivable_writeoff']).exists():fail('Only wholly unpaid, unadjusted invoices can acquire foreign terms.')
    if money(qty*rate)!=bill.amount:fail('Foreign amount multiplied by its original rate must exactly match the posted AFN invoice total. Review the original invoice before registering terms.')
    item=ForeignExposure.objects.create(business=ctx.business,invoice=bill,currency=code,foreign_amount=qty,initial_rate=rate,source=doc)
    ctx.lines.update(bill.product_lines);doc.reference=bill;doc.party=bill.party;doc.location=bill.location
    return {'exposure':item.id,'invoice':bill.id,'foreign_amount':str(qty),'functional_amount':str(bill.amount),'currency':code,'revenue_posted':False}

def settle(ctx,p,doc):
    item=get_obj(ctx,ForeignExposure,p['exposure']);bill=get_obj(ctx,Document,item.invoice_id);receivable=bill.kind in {'sale','opening_receivable'}
    ctx.require('sales.collect' if receivable else 'purchases.pay');ctx.lines.update(bill.product_lines)
    chronological(item.movements,doc.date,bill.date);remaining,carrying=exposure_balance(item);qty=amount(p['foreign_amount'])
    if qty>remaining:fail('Foreign settlement exceeds the contractual balance; unallocated foreign deposits require a separate workflow.')
    released=carrying if qty==remaining else money(carrying*qty/remaining)
    rate=exchange_rate(ctx,p,doc,item.currency);market=money(qty*rate);wallet=None
    if p.get('wallet'):
        wallet=get_obj(ctx,ForeignWallet,p['wallet'])
        if wallet.currency!=item.currency:fail('Invoice and settlement wallet currencies differ.')
        if receivable:wallet_in(ctx,wallet,qty,market,doc);cash_value=market
        else:cash_value=wallet_release(ctx,wallet,qty,doc)
        location=wallet.location;cash=wallet_code(wallet)
    else:
        location=get_obj(ctx,Location,p.get('location') or bill.location_id);cash=p.get('cash_account','CASH');cash_value=market
        if cash not in {'CASH','BANK'}:fail('Select an AFN CASH/BANK account or a foreign wallet.')
    sign=Decimal(1) if receivable else Decimal(-1)
    lines=[signed(cash,sign*cash_value,location.id),signed('AR' if receivable else 'AP',-sign*released,bill.location_id,bill.party_id),difference(sign*(cash_value-released),location.id)]
    journal(ctx,doc,lines)
    ForeignMovement.objects.create(business=ctx.business,exposure=item,document=doc,quantity=-qty,base_value=-released,kind='settlement')
    previous=Allocation.objects.filter(invoice=bill).aggregate(v=Sum('amount'))['v'] or ZERO
    historical=bill.amount-previous if qty==remaining else money(bill.amount*qty/item.foreign_amount)
    if historical:Allocation.objects.create(document=doc,invoice=bill,amount=historical)
    doc.reference=bill;doc.party=bill.party;doc.location=location;doc.amount=cash_value
    return {'exposure':item.id,'invoice':bill.id,'currency':item.currency,'foreign_amount':str(qty),'functional_cash':str(cash_value),'carrying_released':str(released),'exchange_gain':str(sign*(cash_value-released)),'foreign_remaining':str(remaining-qty),'functional_remaining':str(carrying-released),'rate':str(rate),'wallet':wallet.id if wallet else None,'wallet_basis':'weighted carrying value' if wallet and not receivable else 'transaction rate'}

def exchange(ctx,p,doc):
    wallet=get_obj(ctx,ForeignWallet,p['wallet']);qty=amount(p['foreign_amount']);rate=exchange_rate(ctx,p,doc,wallet.currency);paid=money(qty*rate);cash=p.get('cash_account','CASH');direction=p.get('direction')
    if cash not in {'CASH','BANK'} or direction not in {'buy','sell'}:fail('Choose buy/sell and an AFN CASH/BANK account.')
    location=get_obj(ctx,Location,p.get('location') or wallet.location_id);fee=money(nonnegative(p.get('fee',0)))
    if direction=='buy':
        wallet_in(ctx,wallet,qty,paid,doc);lines=[signed(wallet_code(wallet),paid,wallet.location_id),signed(cash,-paid,location.id)];gain=ZERO
    else:
        released=wallet_release(ctx,wallet,qty,doc);gain=paid-released
        lines=[signed(cash,paid,location.id),signed(wallet_code(wallet),-released,wallet.location_id),difference(gain,location.id)]
    if fee:lines.extend([signed('BANK_FEES',fee,location.id),signed(cash,-fee,location.id)])
    journal(ctx,doc,lines);doc.location=location;doc.amount=paid+fee
    return {'wallet':wallet.id,'currency':wallet.currency,'foreign_amount':str(qty),'rate':str(rate),'functional_amount':str(paid),'fee':str(fee),'exchange_gain':str(gain),'carrying_released':str(released if direction=='sell' else paid),'direction':direction}

def transit_value(item):return money(item.carrying_amount+(item.adjustments.filter(document__state='posted').aggregate(v=Sum('base_value'))['v'] or ZERO))

def remit_dispatch(ctx,p,doc):
    source=get_obj(ctx,ForeignWallet,p['source_wallet']);target=get_obj(ctx,ForeignWallet,p['destination_wallet']);qty=amount(p['foreign_amount'])
    if source.id==target.id or source.currency!=target.currency:fail('Choose different wallets in the same currency.')
    value=wallet_release(ctx,source,qty,doc)
    item=Remittance.objects.create(business=ctx.business,source_wallet=source,destination_wallet=target,foreign_amount=qty,carrying_amount=value,reference=text(p,'reference',250),source=doc)
    journal(ctx,doc,[signed('FX_TRANSIT',value,target.location_id),signed(wallet_code(source),-value,source.location_id)])
    fee=money(nonnegative(p.get('fee',0)))
    if fee:journal(ctx,doc,[signed('BANK_FEES',fee,source.location_id),signed('CASH',-fee,source.location_id)])
    doc.location=source.location;doc.amount=value+fee
    return {'remittance':item.id,'state':'in_transit','currency':source.currency,'foreign_amount':str(qty),'carrying_amount':str(value),'external_sale':False}

def remit_receive(ctx,p,doc):
    item=get_obj(ctx,Remittance,p['remittance']);target=get_obj(ctx,ForeignWallet,item.destination_wallet_id)
    if item.completed_by_id:fail('This remittance has already been received.')
    if doc.date<item.source.date:fail('Receipt cannot precede dispatch.')
    chronological(item.adjustments,doc.date);value=transit_value(item);wallet_in(ctx,target,item.foreign_amount,value,doc)
    journal(ctx,doc,[signed(wallet_code(target),value,target.location_id),signed('FX_TRANSIT',-value,target.location_id)])
    item.completed_by=doc;item.save(update_fields=['completed_by']);doc.reference=item.source;doc.location=target.location;doc.amount=value
    return {'remittance':item.id,'state':'received','foreign_amount':str(item.foreign_amount),'carrying_amount':str(value),'external_sale':False}

def revalue(ctx,p,doc):
    kind=p.get('target_type');rate=None
    if kind=='invoice':
        item=get_obj(ctx,ForeignExposure,p['target']);bill=get_obj(ctx,Document,item.invoice_id);ctx.lines.update(bill.product_lines)
        chronological(item.movements,doc.date,bill.date);qty,old=exposure_balance(item);location=bill.location_id;asset=bill.kind in {'sale','opening_receivable'};control='AR' if asset else 'AP';code=item.currency;party=bill.party_id
    elif kind=='wallet':
        item=get_obj(ctx,ForeignWallet,p['target']);chronological(item.movements,doc.date,item.source.date);qty,old=wallet_balance(item);location=item.location_id;asset=True;control=wallet_code(item);code=item.currency;party=None
    elif kind=='remittance':
        item=get_obj(ctx,Remittance,p['target']);get_obj(ctx,ForeignWallet,item.source_wallet_id)
        if item.completed_by_id:fail('Received remittances cannot be revalued in transit.')
        get_obj(ctx,ForeignWallet,item.destination_wallet_id)
        chronological(item.adjustments,doc.date,item.source.date);qty=item.foreign_amount;old=transit_value(item);location=item.destination_wallet.location_id;asset=True;control='FX_TRANSIT';code=item.source_wallet.currency;party=None
    elif kind=='deposit':
        from .foreign_extensions import get_deposit,deposit_balance,deposit_control
        item=get_deposit(ctx,p['target']);chronological(item.movements,doc.date,item.source.date)
        qty,old=deposit_balance(item);location=item.location_id;asset=item.side=='supplier';control=deposit_control(item);code=item.currency;party=item.party_id
    else:fail('Select invoice, wallet or remittance.')
    if qty<=0:fail('Only open monetary balances can be revalued.')
    rate=exchange_rate(ctx,p,doc,code);new=money(qty*rate);change=new-old
    if not change:fail('The carrying amount already matches this closing rate.')
    signed_change=change if asset else -change
    journal(ctx,doc,[signed(control,signed_change,location,party),difference(signed_change,location)])
    if kind=='invoice':ForeignMovement.objects.create(business=ctx.business,exposure=item,document=doc,quantity=0,base_value=change,kind='revaluation');doc.reference=bill
    elif kind=='wallet':ForeignWalletMovement.objects.create(business=ctx.business,wallet=item,document=doc,quantity=0,base_value=change)
    elif kind=='deposit':
        from .foreign_models import ForeignDepositMovement
        ForeignDepositMovement.objects.create(business=ctx.business,deposit=item,document=doc,quantity=0,base_value=change,kind='revaluation');doc.reference=item.source
    else:RemittanceAdjustment.objects.create(business=ctx.business,remittance=item,document=doc,base_value=change)
    doc.location_id=location;doc.amount=abs(change)
    return {'target_type':kind,'target':item.id,'currency':code,'foreign_balance':str(qty),'old_carrying':str(old),'new_carrying':str(new),'rate':str(rate),'exchange_gain':str(signed_change)}

OPERATIONS={'fx_rate':('finance.fx_rate',record_rate),'fx_wallet':('finance.manage',wallet_create),'fx_opening':('accounting.opening',wallet_opening),'fx_register':('finance.fx',register_exposure),'fx_settle':('finance.fx',settle),'fx_exchange':('finance.fx',exchange),'fx_remit_dispatch':('finance.fx',remit_dispatch),'fx_remit_receive':('finance.fx',remit_receive),'fx_revalue':('accounting.post',revalue)}

def reconcile(ctx):
    from .reports import _entries,_net,_company
    ctx.require('accounting.view');_company(ctx,{});rows=[]
    for code,kind in [('FX_CASH','cash'),('FX_BANK','bank'),('FX_TRANSIT',None)]:
        expected=ZERO
        if kind:
            for wallet in ForeignWallet.objects.filter(business=ctx.business,kind=kind):
                if ctx.location_allowed(wallet.location_id):expected+=wallet_balance(wallet)[1]
        else:
            for remit in Remittance.objects.filter(business=ctx.business,completed_by__isnull=True):
                if ctx.location_allowed(remit.destination_wallet.location_id):expected+=transit_value(remit)
        actual=_net(_entries(ctx,{},period=False).filter(account__code=code))
        rows.append({'control':code,'subledger':str(expected),'ledger':str(actual),'difference':str(actual-expected)})
    from .foreign_models import ForeignDeposit
    from .foreign_extensions import deposit_balance
    for code,side,sign in [('FX_CUSTOMER_DEPOSITS','customer',-1),('FX_SUPPLIER_DEPOSITS','supplier',1)]:
        expected=sum((deposit_balance(item)[1]*sign for item in ForeignDeposit.objects.filter(business=ctx.business,side=side)),ZERO)
        actual=_net(_entries(ctx,{},period=False).filter(account__code=code))
        rows.append({'control':code,'subledger':str(expected),'ledger':str(actual),'difference':str(actual-expected)})
    return {'rows':rows,'difference':str(sum((abs(D(r['difference'])) for r in rows),ZERO)),'basis':'Current foreign wallet and remittance carrying values versus posted AFN control accounts.'}

def _extension(name):
    def handle(ctx,p,doc):
        from .foreign_extensions import OPERATIONS as extensions
        return extensions[name][1](ctx,p,doc)
    return handle

OPERATIONS.update({name:(permission,_extension(name)) for name,permission in {
    'fx_sale':'finance.fx','fx_purchase':'finance.fx','fx_deposit':'finance.fx',
    'fx_deposit_allocate':'finance.fx','fx_refund':'finance.fx',
    'fx_settlement_reverse':'finance.reverse','fx_return':'finance.fx','fx_credit':'finance.fx','fx_deposit_revalue':'accounting.post',
}.items()})
