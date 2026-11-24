"""Append-only opportunities, activities and quotation source links."""
from datetime import date
from django.core.exceptions import PermissionDenied, ValidationError
from .core import Context, D, money, get_obj, get_product, get_warehouse, execute
from .models import Document, Location, Membership, Party
from .crm_models import CRMOpportunity, CRMEvent, CRMActivity

STAGES = ('new', 'qualified', 'quoted', 'negotiation', 'won', 'lost')


def text(value, label, maximum=2000, required=True):
    value = str(value or '').strip()
    if (required and not value) or len(value) > maximum:
        raise ValidationError(f'{label} is required and must fit within {maximum} characters.' if required else f'{label} must fit within {maximum} characters.')
    return value


def day(value):
    try: return date.fromisoformat(str(value))
    except (ValueError, TypeError): raise ValidationError('Use a valid canonical YYYY-MM-DD date.')


def state(item):
    stage, assigned = 'new', item.assigned_id
    for event in item.events.all():
        if event.stage: stage = event.stage
        if event.assigned_id: assigned = event.assigned_id
    return stage, assigned


def scope(ctx, item, acting=False):
    ctx.require('crm.view')
    if item.business_id!=ctx.business.id or not ctx.location_allowed(item.location_id):raise PermissionDenied('Opportunity location is outside your scope.')
    if not all(ctx.line_allowed(line) for line in item.product_lines):
        raise PermissionDenied('Complete opportunity product-line scope is required.')
    # Validate the original document independently, without recursive HTTP guards.
    source=item.source
    if source.business_id!=ctx.business.id or (source.location_id and not ctx.location_allowed(source.location_id)) or (not ctx.has('documents.all_lines') and not set(source.product_lines).issubset(ctx.membership.product_lines)):
        raise PermissionDenied('Original opportunity document is outside your complete scope.')
    stage, assigned = state(item)
    assigned_activity = not acting and assigned != ctx.membership.id and not ctx.has('crm.manage') and not ctx.has('crm.read_all') and any(a.assigned_id==ctx.membership.id for a in item.activities.all())
    if assigned != ctx.membership.id and not assigned_activity and not ctx.has('crm.manage') and (acting or not ctx.has('crm.read_all')):
        raise PermissionDenied('Only the assigned salesperson or a CRM manager may access this opportunity.')
    return stage, assigned


def opportunity_for(ctx, identifier, acting=False, open_only=False):
    item = get_obj(ctx, CRMOpportunity, identifier)
    stage, _ = scope(ctx, item, acting)
    if open_only and stage in ('won', 'lost'): raise ValidationError('This opportunity is closed. Preserve its evidence and create a new opportunity for new demand.')
    return item


def eligible(ctx, item=None, location=None, lines=None):
    location = item.location_id if item else location
    lines = item.product_lines if item else lines or []
    result=[]
    for member in Membership.objects.filter(business=ctx.business, active=True, user__is_active=True).select_related('user'):
        candidate=Context(member.user, ctx.business, member)
        if candidate.has('crm.view') and candidate.has('crm.post') and candidate.location_allowed(location) and all(candidate.line_allowed(line) for line in lines):
            result.append(member)
    return result


def assignee(ctx, identifier, item=None, location=None, lines=None):
    member=get_obj(ctx, Membership, identifier)
    if member.id not in {m.id for m in eligible(ctx,item,location,lines)}: raise ValidationError('Select an active salesperson with CRM and complete opportunity scope.')
    return member


def attach(doc, item):
    from django.db.models import Max
    activity_dates=item.activities.aggregate(last=Max('source__date'),finished=Max('completed_by__date'))
    dates=[item.source.date,item.events.aggregate(last=Max('source__date'))['last'],activity_dates['last'],activity_dates['finished']]
    if doc.date < max(value for value in dates if value):raise ValidationError('Follow-up events cannot be backdated before later opportunity evidence.')
    doc.location_id=item.location_id;doc.party_id=item.party_id;doc.reference=item.source


def create(ctx,p,doc):
    ctx.require('crm.view')
    location=get_obj(ctx,Location,p['location'])
    lines=p.get('product_lines')
    if not isinstance(lines,list) or not lines or any(line not in ('sponge','adhesive','shared') or not ctx.line_allowed(line) for line in lines):
        raise PermissionDenied('Select at least one authorized product line.')
    lines=sorted(set(lines));member=assignee(ctx,p.get('assigned') or ctx.membership.pk,location=location.pk,lines=lines)
    if member.id!=ctx.membership.id:ctx.require('crm.manage')
    party=get_obj(ctx,Party,p['party']) if p.get('party') else None
    if party and party.kind!='customer':raise ValidationError('Choose a customer account.')
    expected=D(p.get('expected_amount','0'))
    if expected<0 or money(expected)!=expected:raise ValidationError('Expected AFN amount must be nonnegative with at most two decimal places.')
    if ctx.business.currency!='AFN':raise ValidationError('CRM expected values currently use AFN only.')
    expected_date=day(p['expected_date'])
    if expected_date<doc.date:raise ValidationError('Expected closing date cannot precede the opportunity date.')
    item=CRMOpportunity.objects.create(business=ctx.business,title=text(p.get('title'),'Opportunity title',180),location=location,product_lines=lines,assigned=member,party=party,
        prospect_name=text(party.name if party else p.get('prospect_name'),'Prospect/customer name',180),phone=text(party.phone if party else p.get('phone'),'Phone',80,False),
        expected_amount=expected,expected_date=expected_date,note=text(p.get('note'),'Initial note',2000,False),source=doc)
    doc.location=location;doc.party=party;doc.amount=expected;ctx.lines.update(lines)
    return {'opportunity':item.id,'stage':'new','assigned':member.id,'expected_amount':str(expected),'financial_posting':False,'basis':'Expected commercial value only; not sales, cash or receivables.'}


def transition(ctx,p,doc):
    item=opportunity_for(ctx,p['opportunity'],True,True)
    stage=text(p.get('stage'),'Stage',20)
    current,_=state(item)
    if stage not in STAGES or stage==current:raise ValidationError('Select a different supported opportunity stage.')
    reason=text(p.get('reason'),'Stage decision reason')
    if stage in ('quoted','won'):
        from .operations import _commercial_cancelled
        if not any(not _commercial_cancelled(ctx,event.quotation) for event in item.events.filter(quotation__isnull=False).select_related('quotation')):
            raise ValidationError('Create a current linked quotation before marking quoted or won. Won is commercial evidence, not revenue.')
    event=CRMEvent.objects.create(business=ctx.business,opportunity=item,kind='stage',stage=stage,reason=reason,source=doc)
    attach(doc,item);ctx.lines.update(item.product_lines)
    return {'opportunity':item.id,'event':event.id,'stage':stage,'reason':reason,'financial_posting':False,'linked_quotes_preserved':True,'quotation_cancellation_required_separately':stage=='lost'}


def assign(ctx,p,doc):
    ctx.require('crm.manage');item=opportunity_for(ctx,p['opportunity'],True,True)
    member=assignee(ctx,p['assigned'],item);_,previous=state(item)
    if member.id==previous:raise ValidationError('This salesperson is already assigned.')
    event=CRMEvent.objects.create(business=ctx.business,opportunity=item,kind='assignment',assigned=member,reason=text(p.get('reason'),'Assignment reason'),source=doc)
    attach(doc,item);ctx.lines.update(item.product_lines)
    return {'opportunity':item.id,'event':event.id,'assigned':member.id,'financial_posting':False,'existing_activity_assignments_preserved':True}


def activity(ctx,p,doc):
    item=opportunity_for(ctx,p['opportunity'],True,True)
    _,owner=state(item);member=assignee(ctx,p.get('assigned') or owner,item)
    if member.id!=ctx.membership.id:ctx.require('crm.manage')
    due=day(p['due_date'])
    if due<doc.date:raise ValidationError('Activity due date cannot precede its creation date.')
    item_activity=CRMActivity.objects.create(business=ctx.business,opportunity=item,assigned=member,due_date=due,task=text(p.get('task'),'Follow-up task',500),source=doc)
    attach(doc,item);ctx.lines.update(item.product_lines)
    return {'opportunity':item.id,'activity':item_activity.id,'due_date':due,'assigned':member.id,'financial_posting':False,'external_message_sent':False}


def finish_activity(ctx,p,doc):
    item_activity=get_obj(ctx,CRMActivity,p['activity']);item=opportunity_for(ctx,item_activity.opportunity_id)
    if item_activity.assigned_id!=ctx.membership.id:ctx.require('crm.manage')
    if item_activity.completed_by_id:raise ValidationError('This follow-up is already completed.')
    if doc.date<item_activity.source.date:raise ValidationError('Completion cannot precede activity creation.')
    note=text(p.get('reason'),'Completed action and outcome')
    item_activity.completed_by=doc;item_activity.save(update_fields=['completed_by'])
    attach(doc,item);ctx.lines.update(item.product_lines)
    return {'opportunity':item.id,'activity':item_activity.id,'state':'done','outcome':note,'financial_posting':False,'external_message_sent':False}


def note(ctx,p,doc):
    item=opportunity_for(ctx,p['opportunity'],True)
    event=CRMEvent.objects.create(business=ctx.business,opportunity=item,kind='note',reason=text(p.get('note'),'Follow-up note'),source=doc)
    attach(doc,item);ctx.lines.update(item.product_lines)
    return {'opportunity':item.id,'event':event.id,'financial_posting':False}


def quote(ctx,p,doc):
    ctx.require('sales.post');item=opportunity_for(ctx,p['opportunity'],True,True)
    warehouse=get_warehouse(ctx,p['warehouse'])
    if warehouse.location_id!=item.location_id or warehouse.kind=='transit':raise ValidationError('Choose an actual warehouse at the opportunity location.')
    customer=get_obj(ctx,Party,p.get('party') or item.party_id)
    if customer.kind!='customer' or (item.party_id and customer.id!=item.party_id):raise ValidationError('Choose the original customer, or a customer account for this prospect.')
    prior=item.events.filter(quotation__isnull=False).select_related('quotation').first()
    if prior and prior.quotation.party_id!=customer.id:raise ValidationError('Use the customer account already linked to this prospect quotation.')
    lines=p.get('lines',[])
    if not isinstance(lines,list) or not 1<=len(lines)<=100:raise ValidationError('A linked quotation needs one to 100 items.')
    for line in lines:
        product=get_product(ctx,line['product'])
        if product.line not in item.product_lines or product.kind in ('raw','service') or not product.active:raise ValidationError('Choose active saleable items from the opportunity product lines.')
        if product.unit=='cm' and not (line.get('length_mm') and line.get('width_mm')):raise ValidationError('Sponge quotation requires the full-face length and width, not a grade-to-weight conversion.')
    previous=getattr(ctx,'crm_quote_source',None);ctx.crm_quote_source=item.id
    try:quote_doc=execute(ctx,'quotation',{'date':str(doc.date),'warehouse':warehouse.id,'party':customer.id,'lines':lines,'crm_opportunity':item.id},f'crm-quotation-{item.id}-{doc.id}')
    finally:ctx.crm_quote_source=previous
    CRMEvent.objects.create(business=ctx.business,opportunity=item,kind='quotation',quotation=quote_doc,reason=text(p.get('note'),'Quotation note',2000,False),source=doc)
    attach(doc,item);doc.warehouse=warehouse;doc.party=customer;doc.amount=quote_doc.amount;ctx.lines.update(item.product_lines)
    return {'opportunity':item.id,'quotation':quote_doc.id,'quotation_number':quote_doc.number,'expected_amount':str(item.expected_amount),'quotation_amount':str(quote_doc.amount),'financial_posting':False,'recognition':'Quotation only; no reservation, stock movement, revenue, cash or receivable.'}


def document_guard(ctx,doc):
    # Do not bypass assignment, contact or whole-line scope via generic documents.
    if doc.kind=='quotation' and doc.data.get('crm_opportunity'):
        opportunity_for(ctx,doc.data['crm_opportunity'])
    if doc.kind not in OPERATIONS:return
    identifier=doc.result.get('opportunity') or doc.data.get('opportunity')
    if identifier:opportunity_for(ctx,identifier)
    elif doc.data.get('activity'):
        activity_item=get_obj(ctx,CRMActivity,doc.data['activity']);opportunity_for(ctx,activity_item.opportunity_id)
    else:
        ctx.require('crm.view')
        get_obj(ctx,Location,doc.data.get('location'))
        if not all(ctx.line_allowed(line) for line in doc.data.get('product_lines',[])):raise PermissionDenied('Complete opportunity product-line scope is required.')
        if doc.created_by_id!=ctx.user.id and not (ctx.has('crm.manage') or ctx.has('crm.read_all')):raise PermissionDenied('Opportunity draft is restricted.')


OPERATIONS={'crm_create':('crm.post',create),'crm_transition':('crm.post',transition),'crm_assign':('crm.manage',assign),'crm_activity':('crm.post',activity),'crm_activity_done':('crm.post',finish_activity),'crm_note':('crm.post',note),'crm_quote':('crm.post',quote)}


def enrich_registry(registry):
    """Commercial conversion cannot bypass the linked original CRM authority."""
    result=dict(registry)
    for action in ('quotation','sales_order','order_cancel'):
        permission,handler=result[action]
        def guarded(ctx,p,doc,_action=action,_handler=handler):
            if _action=='quotation' and p.get('crm_opportunity'):
                if getattr(ctx,'crm_quote_source',None)!=p['crm_opportunity']:raise ValidationError('Create linked CRM quotations through the reviewed CRM workflow.')
                opportunity_for(ctx,p['crm_opportunity'],True,True)
            identifier=p.get('quotation') if _action=='sales_order' else p.get('order') if _action=='order_cancel' else None
            if identifier:
                original=get_obj(ctx,Document,identifier)
                if original.kind=='quotation' and original.data.get('crm_opportunity'):opportunity_for(ctx,original.data['crm_opportunity'])
            return _handler(ctx,p,doc)
        result[action]=(permission,guarded)
    return result
