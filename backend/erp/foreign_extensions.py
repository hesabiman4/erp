"""Integrated FX invoices, refundable credits, linked corrections and settlements.

All entry points run under core.execute. The general ledger remains AFN; exact
foreign contractual balances have separate append-only movement ledgers.
"""
from decimal import Decimal, localcontext
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum
from .models import Document, Entry, Allocation, Location, Party, Product, ForeignExposure, ForeignMovement, ForeignWallet, ForeignWalletMovement
from .foreign_models import ForeignDeposit, ForeignDepositMovement
from .core import D, money, get_obj, get_product, journal, execute, balance
from .foreign import (ZERO, amount, currency, exchange_rate, chronological, exposure_balance,
                      wallet_balance, wallet_in, wallet_release, wallet_code, signed, difference)


def fail(message):
    raise ValidationError(message)


def posted(ctx, ident, kinds=None):
    doc=get_obj(ctx,Document,ident)
    if doc.state!='posted' or (kinds and doc.kind not in kinds):fail('Select an eligible posted document.')
    ctx.lines.update(doc.product_lines)
    return doc


def deposit_balance(item, through=None):
    query=item.movements.filter(document__state='posted')
    if through:query=query.filter(document__date__lte=through)
    sums=query.aggregate(q=Sum('quantity'),v=Sum('base_value'))
    return item.foreign_amount+(sums['q'] or ZERO),money(item.base_value+(sums['v'] or ZERO))


def deposit_control(item):
    return 'FX_CUSTOMER_DEPOSITS' if item.side=='customer' else 'FX_SUPPLIER_DEPOSITS'


def get_deposit(ctx, ident):
    item=get_obj(ctx,ForeignDeposit,ident)
    posted(ctx,item.source_id)
    if not ctx.has('documents.all_lines') and item.movements.exclude(document__product_lines__contained_by=ctx.membership.product_lines).exists():
        raise PermissionDenied('The foreign deposit includes a restricted product line.')
    return item


def exposure(ctx, ident):
    item=get_obj(ctx,ForeignExposure,ident)
    bill=posted(ctx,item.invoice_id)
    if bill.kind not in {'sale','purchase_bill','opening_receivable','opening_payable'}:fail('Unsupported foreign invoice type.')
    return item,bill,bill.kind in {'sale','opening_receivable'}


def _historical_allocation(ctx,doc,item,bill,qty,remaining):
    previous=Allocation.objects.filter(invoice=bill).aggregate(v=Sum('amount'))['v'] or ZERO
    available=max(ZERO,money(bill.amount-previous))
    historical=available if qty==remaining else min(available,money(bill.amount*qty/item.foreign_amount))
    if historical:Allocation.objects.create(document=doc,invoice=bill,amount=historical)
    return historical


def _portion(value,qty,remaining):
    return value if qty==remaining else money(value*qty/remaining)


def _snapshot_lines(ctx,p,rate,purchasing=False):
    requested=p.get('lines',[])
    if not requested:fail('Enter at least one foreign-priced line.')
    if p.get('tax_rule') or D(p.get('landed_cost','0')):fail('Integrated foreign invoices currently exclude tax and separate landed-cost amounts. Record supported controlled cost adjustments separately.')
    if D(p.get('paid','0')) or p.get('order') or p.get('sales_order') or p.get('quotation') or p.get('receipt'):
        fail('Use an unpaid delivered foreign invoice; settle it with the linked foreign settlement workflow. Pre-existing orders/receipts require separate reviewed integration.')
    converted=[];snapshots=[];foreign_total=ZERO
    from .operations import sheet_thickness
    for index,row in enumerate(requested):
        product=get_product(ctx,row['product'])
        qty=sheet_thickness(row)*D(row.get('sheet_count','1'))/10 if product.unit=='cm' and not purchasing else D(row['quantity'])
        if qty<=0:fail('Invoice quantities must be positive.')
        price=D(row.get('foreign_unit_cost' if purchasing else 'foreign_unit_price','0'))
        discount=money(D(row.get('foreign_discount','0')))
        if price<0 or discount<0:fail('Foreign prices and discounts cannot be negative.')
        if discount and not purchasing:ctx.require('sales.discount')
        gross=money(qty*price);net=money(gross-discount)
        if net<0 or (not net and not row.get('free_issue')):fail('A foreign line requires a positive net amount or an authorized free issue.')
        if purchasing and discount:fail('Use a net foreign unit cost for purchases; purchase discount lines are not implemented.')
        foreign_total+=net
        snapshots.append({'index':index,'product':product.id,'quantity':str(qty),'foreign_unit_cost' if purchasing else 'foreign_unit_price':str(price),'foreign_discount':str(discount),'foreign_amount':str(net)})
        converted.append(dict(row))
    foreign_total=amount(foreign_total);base_total=money(foreign_total*rate);remaining=base_total
    for index,(row,snapshot) in enumerate(zip(converted,snapshots)):
        target=remaining if index==len(converted)-1 else money(D(snapshot['foreign_amount'])*rate)
        if target<0:fail('The converted line allocation is below zero; review currency precision.')
        remaining-=target
        with localcontext() as calc:
            calc.prec=40
            unit=target/D(snapshot['quantity'])
        row['unit_cost' if purchasing else 'unit_price']=str(unit)
        if not purchasing:row['discount']='0'
        snapshot['functional_amount']=str(target)
    return converted,{'currency':p['foreign_currency'],'foreign_amount':str(foreign_total),'functional_amount':str(base_total),'initial_rate':str(rate),'lines':snapshots,'rate_reference':p.get('rate_reference',''),'rate_record':p.get('rate_record')}


def fx_sale(ctx,p,doc):
    ctx.require('sales.post');ctx.require('sales.price')
    code=currency(ctx,p['foreign_currency']);rate=exchange_rate(ctx,p,doc,code)
    lines,snapshot=_snapshot_lines(ctx,p,rate)
    translated={**p,'lines':lines,'paid':'0','foreign_snapshot':snapshot}
    doc.kind='sale';doc.data=translated
    from .operations import sale
    from .growth_hooks import wrap
    result=wrap('sale',sale)(ctx,translated,doc)
    if doc.amount!=D(snapshot['functional_amount']):fail('Converted invoice does not reconcile at the contractual rate.')
    item=ForeignExposure.objects.create(business=ctx.business,invoice=doc,currency=code,foreign_amount=D(snapshot['foreign_amount']),initial_rate=rate,source=doc)
    return {**result,'exposure':item.id,'foreign_snapshot':snapshot,'foreign_invoice':True,'invoice':doc.id}


def fx_purchase(ctx,p,doc):
    ctx.require('purchases.post')
    code=currency(ctx,p['foreign_currency']);rate=exchange_rate(ctx,p,doc,code)
    lines,snapshot=_snapshot_lines(ctx,p,rate,purchasing=True)
    receipt_payload={**p,'date':doc.date.isoformat(),'lines':lines,'foreign_snapshot':snapshot}
    receipt=execute(ctx,'purchase_receive',receipt_payload,f'fx-receipt:{doc.id}')
    translated={'date':doc.date.isoformat(),'receipt':receipt.id,'supplier':p.get('supplier') or p.get('party'),'supplier_reference':p.get('supplier_reference',''),'foreign_snapshot':snapshot}
    doc.kind='purchase_bill';doc.data=translated
    from .operations import purchase_bill
    result=purchase_bill(ctx,translated,doc)
    if doc.amount!=D(snapshot['functional_amount']):fail('Converted purchase does not reconcile at the contractual rate.')
    item=ForeignExposure.objects.create(business=ctx.business,invoice=doc,currency=code,foreign_amount=D(snapshot['foreign_amount']),initial_rate=rate,source=doc)
    return {**result,'exposure':item.id,'foreign_snapshot':snapshot,'foreign_invoice':True,'invoice':doc.id,'receipt':receipt.id}


def _deposit_create(ctx,doc,party,location,code,qty,value,side):
    return ForeignDeposit.objects.create(business=ctx.business,source=doc,party=party,location=location,currency=code,side=side,foreign_amount=qty,base_value=value)


def _money_side(ctx,p,doc,code,qty,rate,receiving,default_location):
    market=money(qty*rate)
    if p.get('wallet'):
        wallet=get_obj(ctx,ForeignWallet,p['wallet'])
        if wallet.currency!=code:fail('Wallet currency does not match the contract currency.')
        if receiving:wallet_in(ctx,wallet,qty,market,doc);value=market
        else:value=wallet_release(ctx,wallet,qty,doc)
        return wallet_code(wallet),value,wallet.location
    location=get_obj(ctx,Location,p.get('location') or default_location)
    cash=p.get('cash_account','CASH')
    if cash not in {'CASH','BANK'}:fail('Select AFN cash/bank or a matching foreign wallet.')
    return cash,market,location


def fx_deposit(ctx,p,doc):
    if p.get('classification')!='refundable_monetary':fail('Only refundable monetary deposits are supported. Goods/services advances need historical-rate recognition under a separately implemented policy.')
    party=get_obj(ctx,Party,p['party']);side=p.get('side')
    if side not in {'customer','supplier'} or party.kind!=side:fail('Choose the correct customer/supplier and deposit side.')
    ctx.require('sales.collect' if side=='customer' else 'purchases.pay')
    code=currency(ctx,p['foreign_currency']);qty=amount(p['foreign_amount']);rate=exchange_rate(ctx,p,doc,code);market=money(qty*rate)
    cash,value,location=_money_side(ctx,p,doc,code,qty,rate,side=='customer',p.get('location'))
    item=_deposit_create(ctx,doc,party,location,code,qty,market,side)
    sign=Decimal(1) if side=='customer' else Decimal(-1)
    journal(ctx,doc,[signed(cash,sign*value,location.id),signed(deposit_control(item),-sign*market,location.id,party.id),difference(sign*(value-market),location.id)])
    doc.party=party;doc.location=location;doc.amount=max(value,market)
    return {'deposit':item.id,'side':side,'currency':code,'foreign_amount':str(qty),'functional_amount':str(market),'functional_cash':str(value),'rate':str(rate),'classification':'refundable_monetary','exchange_gain':str(sign*(value-market))}


def fx_deposit_allocate(ctx,p,doc):
    deposit=get_deposit(ctx,p['deposit']);item,bill,receivable=exposure(ctx,p['exposure'])
    ctx.require('sales.collect' if receivable else 'purchases.pay')
    if deposit.party_id!=bill.party_id or deposit.currency!=item.currency or deposit.side!=('customer' if receivable else 'supplier'):fail('Deposit and invoice must have the same party, currency and side.')
    chronological(deposit.movements,doc.date,deposit.source.date);chronological(item.movements,doc.date,bill.date)
    available,deposit_value=deposit_balance(deposit);remaining,invoice_value=exposure_balance(item);qty=amount(p['foreign_amount'])
    if qty>available or qty>remaining:fail('Allocation exceeds the remaining foreign deposit or invoice.')
    released_deposit=_portion(deposit_value,qty,available);released_invoice=_portion(invoice_value,qty,remaining);sign=Decimal(1) if receivable else Decimal(-1)
    journal(ctx,doc,[signed(deposit_control(deposit),sign*released_deposit,deposit.location_id,bill.party_id),signed('AR' if receivable else 'AP',-sign*released_invoice,bill.location_id,bill.party_id),difference(sign*(released_deposit-released_invoice),deposit.location_id)])
    ForeignDepositMovement.objects.create(business=ctx.business,deposit=deposit,document=doc,quantity=-qty,base_value=-released_deposit,kind='allocation')
    ForeignMovement.objects.create(business=ctx.business,exposure=item,document=doc,quantity=-qty,base_value=-released_invoice,kind='allocation')
    _historical_allocation(ctx,doc,item,bill,qty,remaining)
    doc.reference=deposit.source;doc.party=bill.party;doc.location=deposit.location;doc.amount=max(released_deposit,released_invoice)
    return {'deposit':deposit.id,'exposure':item.id,'invoice':bill.id,'currency':item.currency,'foreign_amount':str(qty),'deposit_carrying_released':str(released_deposit),'carrying_released':str(released_invoice),'exchange_gain':str(sign*(released_deposit-released_invoice)),'foreign_remaining':str(remaining-qty),'deposit_remaining':str(available-qty),'cash_changed':False}


def fx_refund(ctx,p,doc):
    deposit=get_deposit(ctx,p['deposit']);customer=deposit.side=='customer'
    ctx.require('sales.refund' if customer else 'purchases.pay')
    if not str(p.get('reason','')).strip():fail('A refund requires its approved reason.')
    chronological(deposit.movements,doc.date,deposit.source.date);available,carrying=deposit_balance(deposit);qty=amount(p['foreign_amount'])
    if qty>available:fail('Refund exceeds the remaining foreign deposit credit.')
    rate=exchange_rate(ctx,p,doc,deposit.currency);released=_portion(carrying,qty,available)
    cash,value,location=_money_side(ctx,p,doc,deposit.currency,qty,rate,not customer,deposit.location_id)
    sign=Decimal(1) if customer else Decimal(-1)
    journal(ctx,doc,[signed(deposit_control(deposit),sign*released,deposit.location_id,deposit.party_id),signed(cash,-sign*value,location.id),difference(sign*(released-value),location.id)])
    ForeignDepositMovement.objects.create(business=ctx.business,deposit=deposit,document=doc,quantity=-qty,base_value=-released,kind='refund')
    doc.reference=deposit.source;doc.party=deposit.party;doc.location=location;doc.amount=max(released,value)
    return {'deposit':deposit.id,'currency':deposit.currency,'foreign_amount':str(qty),'functional_cash':str(value),'carrying_released':str(released),'foreign_remaining':str(available-qty),'exchange_gain':str(sign*(released-value)),'rate':str(rate),'side':deposit.side}


def fx_settlement_reverse(ctx,p,doc):
    ctx.require('finance.reverse')
    source=posted(ctx,p['settlement'],{'fx_settle'})
    if not str(p.get('reason','')).strip():fail('Settlement reversal requires an approved reason.')
    if source.children.filter(kind='fx_settlement_reverse',state='posted').exists():fail('Settlement is already reversed.')
    movement=ForeignMovement.objects.filter(document=source,kind='settlement').first()
    if not movement:fail('The source is not a supported foreign invoice settlement.')
    item,bill,receivable=exposure(ctx,movement.exposure_id);ctx.require('sales.collect' if receivable else 'purchases.pay')
    doc.reference=source;doc.party=bill.party;doc.location=source.location;doc.amount=max(source.amount,-movement.base_value)
    doc.save(update_fields=['reference','party','location','amount'])
    chronological(item.movements,doc.date,bill.date)
    if item.movements.filter(pk__gt=movement.pk,document__state='posted').exists():fail('Only the latest invoice movement can be reversed. Resolve later settlements, allocations, credits or revaluations first.')
    for moved in ForeignWalletMovement.objects.filter(document=source).select_related('wallet'):
        wallet=get_obj(ctx,ForeignWallet,moved.wallet_id)
        if wallet.movements.filter(pk__gt=moved.pk,document__state='posted').exists():fail('The settlement wallet has later movements; an exact reversal would corrupt its carrying cost.')
        chronological(wallet.movements,doc.date,wallet.source.date)
        qty,value=wallet_balance(wallet)
        if moved.quantity>qty or moved.base_value>value:fail('Insufficient original foreign wallet balance for reversal.')
        ForeignWalletMovement.objects.create(business=ctx.business,wallet=wallet,document=doc,quantity=-moved.quantity,base_value=-moved.base_value)
    entries=[]
    for entry in source.entries.select_related('account','location','party','warehouse','employee'):
        if entry.location_id:get_obj(ctx,Location,entry.location_id)
        instrument=None
        if entry.account.code in {'CASH','BANK'}:
            from .money_instruments import legacy_for,instrument_balance
            instrument=getattr(getattr(entry,'money_link',None),'instrument',None)
            if not instrument and entry.location_id:instrument=legacy_for(ctx,entry.location_id,entry.account.code)
            available=instrument_balance(instrument,doc.date) if instrument else balance(ctx,entry.account.code,location=entry.location_id,through=doc.date)
            if entry.debit and available<entry.debit:fail('Insufficient AFN funds to reverse this customer settlement.')
        entries.append({'account':entry.account.code,'debit':entry.credit,'credit':entry.debit,'location':entry.location,'party':entry.party,'warehouse':entry.warehouse,'employee':entry.employee,'line':entry.line,'instrument':getattr(instrument,'pk',None)})
    journal(ctx,doc,entries)
    ForeignMovement.objects.create(business=ctx.business,exposure=item,document=doc,quantity=-movement.quantity,base_value=-movement.base_value,kind='reversal')
    for original in source.allocations.all():Allocation.objects.create(document=doc,invoice=original.invoice,amount=-original.amount)
    doc.reference=source;doc.party=bill.party;doc.location=source.location;doc.amount=max(source.amount,-movement.base_value)
    return {'settlement':source.id,'invoice':bill.id,'exposure':item.id,'currency':item.currency,'foreign_amount':str(-movement.quantity),'carrying_restored':str(-movement.base_value),'functional_cash_reversed':source.result.get('functional_cash'),'reason':p['reason']}


def _credited_total(bill):
    return sum((D(item.result.get('foreign_credit','0')) for item in bill.children.filter(state='posted')),ZERO)


def _apply_credit(ctx,p,doc,item,bill,receivable,foreign_credit,historical_credit,historical_entries=None):
    chronological(item.movements,doc.date,bill.date)
    if foreign_credit>item.foreign_amount-_credited_total(bill):fail('Credits/returns exceed the original contractual foreign invoice amount.')
    remaining,carrying=exposure_balance(item);applied=min(foreign_credit,remaining);released=_portion(carrying,applied,remaining) if applied else ZERO
    extra=foreign_credit-applied;rate=exchange_rate(ctx,p,doc,item.currency);deposit_value=money(extra*rate);sign=Decimal(1) if receivable else Decimal(-1)
    entries=list(historical_entries or [])
    for original in doc.entries.select_related('account','location','warehouse','party','employee'):
        entries.append({'account':original.account.code,'debit':original.debit,'credit':original.credit,'location':original.location,'warehouse':original.warehouse,'party':original.party,'employee':original.employee,'line':original.line})
    doc.entries.all().delete()
    if applied:
        entries.append(signed('AR' if receivable else 'AP',-sign*released,bill.location_id,bill.party_id))
        ForeignMovement.objects.create(business=ctx.business,exposure=item,document=doc,quantity=-applied,base_value=-released,kind='credit')
        _historical_allocation(ctx,doc,item,bill,applied,remaining)
    deposit=None
    if extra:
        deposit=_deposit_create(ctx,doc,bill.party,bill.location,item.currency,extra,deposit_value,'customer' if receivable else 'supplier')
        entries.append(signed(deposit_control(deposit),-sign*deposit_value,bill.location_id,bill.party_id))
    gain=sign*(historical_credit-released-deposit_value)
    entries.append(difference(gain,bill.location_id));journal(ctx,doc,entries)
    return {'exposure':item.id,'invoice':bill.id,'currency':item.currency,'foreign_credit':str(foreign_credit),'historical_credit':str(historical_credit),'foreign_applied':str(applied),'carrying_released':str(released),'functional_credit_total':str(released+deposit_value),'deposit':deposit.id if deposit else None,'foreign_deposit':str(extra),'foreign_remaining':str(remaining-applied),'exchange_gain':str(gain),'rate':str(rate),'deposit_amount':'0','deposit_side':None}


def fx_return(ctx,p,doc):
    item,bill,receivable=exposure(ctx,p['exposure'])
    ctx.require('sales.refund' if receivable else 'purchases.post')
    if bill.kind not in {'sale','purchase_bill'}:fail('Opening balances have no physical inventory to return.')
    snapshot=bill.data.get('foreign_snapshot') or bill.result.get('foreign_snapshot')
    if not snapshot:fail('This registered legacy invoice lacks foreign line snapshots; use a reviewed foreign price credit or correct its contract first.')
    if bill.children.filter(kind='fx_credit',state='posted').exists():fail('An invoice with price-only credits requires a reviewed combined quantity/price correction; automatic physical return would duplicate that discount.')
    doc.kind='sales_return' if receivable else 'purchase_return'
    translated={**p,'invoice':bill.id}
    if not receivable:translated.update({'bill':bill.id,'receipt':bill.reference_id})
    from .operations import sales_return,purchase_return
    result=(sales_return if receivable else purchase_return)(ctx,translated,doc)
    # Replace only this draft's ordinary AFN debt/credit rows; retain all genuine
    # stock, revenue, COGS, loss and allowance effects from the established handler.
    doc.entries.filter(account__code__in=['AR','AP','DEPOSITS','SUPPLIER_DEPOSITS']).delete()
    Allocation.objects.filter(document=doc).delete()
    previous=bill.children.filter(kind=doc.kind,state='posted');foreign_credit=ZERO;current_qty={}
    for returned in result['lines']:
        original=snapshot['lines'][int(returned['index'])];original_qty=D(original['quantity']);qty=D(returned['quantity'])
        prior_qty=sum((D(line['quantity']) for previous_doc in previous for line in previous_doc.result.get('lines',[]) if int(line['index'])==int(returned['index'])),ZERO)
        prior_qty+=current_qty.get(int(returned['index']),ZERO)
        # Cumulative rounding makes a complete final return exact.
        before=money(D(original['foreign_amount'])*prior_qty/original_qty)
        after=D(original['foreign_amount']) if prior_qty+qty==original_qty else money(D(original['foreign_amount'])*(prior_qty+qty)/original_qty)
        foreign_credit+=after-before
        current_qty[int(returned['index'])]=current_qty.get(int(returned['index']),ZERO)+qty
    if foreign_credit<=0:fail('The returned quantities do not create a positive foreign credit at supported precision.')
    historical=D(result['total']);credit=_apply_credit(ctx,p,doc,item,bill,receivable,foreign_credit,historical)
    if not receivable:
        from .growth_hooks import apply_lots
        apply_lots(ctx,translated,doc)
    doc.data={**translated,'foreign_credit_snapshot':credit};doc.amount=max(historical,D(credit['functional_credit_total']))
    return {**result,**credit,'foreign_return':True}


def fx_credit(ctx,p,doc):
    item,bill,receivable=exposure(ctx,p['exposure']);ctx.require('sales.refund')
    if not receivable or bill.kind!='sale':fail('Price-only foreign credits support sales invoices. Supplier price adjustments require controlled inventory-cost treatment.')
    if not str(p.get('reason','')).strip():fail('A foreign price credit requires its approved reason.')
    qty=amount(p['foreign_amount']);line=p.get('line')
    if line not in {row.get('line') for row in bill.result.get('lines',[])}:fail('Choose a product line actually sold on the original invoice.')
    credited=_credited_total(bill)
    prior_historical=sum((D(child.result.get('historical_credit','0')) for child in bill.children.filter(state='posted')),ZERO)
    historical=max(ZERO,money(bill.amount-prior_historical)) if qty+credited==item.foreign_amount else min(max(ZERO,money(bill.amount-prior_historical)),money(qty*item.initial_rate))
    ctx.lines.add(line)
    credit=_apply_credit(ctx,p,doc,item,bill,True,qty,historical,[{**signed('SALES',historical,bill.location_id,bill.party_id),'line':line}])
    doc.reference=bill;doc.party=bill.party;doc.location=bill.location;doc.amount=max(historical,D(credit['functional_credit_total']))
    return {**credit,'historical_revenue_credit':str(historical),'reason':p['reason'],'physical_stock_changed':False}


def fx_deposit_revalue(ctx,p,doc):
    from .foreign import revalue
    return revalue(ctx,{**p,'target_type':'deposit','target':p['deposit']},doc)


OPERATIONS={
 'fx_sale':('finance.fx',fx_sale),'fx_purchase':('finance.fx',fx_purchase),
 'fx_deposit':('finance.fx',fx_deposit),'fx_deposit_allocate':('finance.fx',fx_deposit_allocate),
 'fx_refund':('finance.fx',fx_refund),'fx_settlement_reverse':('finance.reverse',fx_settlement_reverse),
 'fx_return':('finance.fx',fx_return),'fx_credit':('finance.fx',fx_credit),
 'fx_deposit_revalue':('accounting.post',fx_deposit_revalue),
}


def extension_options(ctx):
    if not any(ctx.has(permission) for permission in ['finance.fx','finance.view','accounting.view']):
        raise PermissionDenied('Foreign monetary information is restricted.')
    result={'deposits':[],'invoices':[],'settlements':[]}
    for deposit in ForeignDeposit.objects.filter(business=ctx.business).select_related('party','source').order_by('-id')[:500]:
        try:
            get_deposit(ctx,deposit.id)
        except PermissionDenied:
            continue
        qty,value=deposit_balance(deposit)
        result['deposits'].append({'id':deposit.id,'number':deposit.source.number,'side':deposit.side,'party':deposit.party_id,'party_name':deposit.party.name,'currency':deposit.currency,'location':deposit.location_id,'foreign_remaining':str(qty),'carrying_amount':str(value),'classification':'refundable_monetary'})
    for item in ForeignExposure.objects.filter(business=ctx.business).select_related('invoice__party').order_by('-id')[:500]:
        try:
            bill=posted(ctx,item.invoice_id)
        except PermissionDenied:
            continue
        qty,value=exposure_balance(item)
        invoice_lines=[]
        returned_documents=list(bill.children.filter(state='posted',kind__in=['sales_return','purchase_return']))
        for row in bill.result.get('lines',[]):
            line={key:row.get(key) for key in ['index','product','product_name','quantity','sheet_count','thickness_mm','line']}
            returned=sum((D(returned_line['quantity']) for returned_doc in returned_documents for returned_line in returned_doc.result.get('lines',[]) if int(returned_line['index'])==int(row['index'])),ZERO)
            line['returnable_quantity']=str(max(ZERO,D(row.get('quantity','0'))-returned));invoice_lines.append(line)
        result['invoices'].append({'id':item.id,'invoice':bill.id,'number':bill.number,'party':bill.party_id,'party_name':bill.party.name,'kind':bill.kind,'warehouse':bill.warehouse_id,'currency':item.currency,'foreign_remaining':str(qty),'carrying_amount':str(value),'initial_rate':str(item.initial_rate),'foreign_credit_remaining':str(item.foreign_amount-_credited_total(bill)),'has_price_credit':bill.children.filter(kind='fx_credit',state='posted').exists(),'lines':invoice_lines,'foreign_snapshot':bill.data.get('foreign_snapshot') or bill.result.get('foreign_snapshot')})
    for source in Document.objects.filter(business=ctx.business,kind='fx_settle',state='posted').order_by('-id')[:500]:
        try:
            posted(ctx,source.id)
        except PermissionDenied:
            continue
        result['settlements'].append({'id':source.id,'number':source.number,'date':source.date.isoformat(),'currency':source.result.get('currency'),'foreign_amount':source.result.get('foreign_amount'),'invoice':source.result.get('invoice'),'reversed':source.children.filter(kind='fx_settlement_reverse',state='posted').exists()})
    return result


from .api import Boundary,response
class ForeignExtensionAPI(Boundary):
    def get(self,request):
        return response(extension_options(self.ctx(request)))
