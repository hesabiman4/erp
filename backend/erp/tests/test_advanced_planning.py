from decimal import Decimal
from uuid import uuid4
import pytest
from django.core.exceptions import ValidationError, PermissionDenied
from erp.tests.test_growth import growth_env, open_block
from erp.tests.test_api import environment, client_for
from erp.core import Context, execute
from erp.models import Document, WorkOrder, Entry, StockMovement, Membership, Block, Product
from erp.advanced_planning import preview_schedule, preview_new_work, planning_board, efficiency, cutting_alternatives, capacity_usage


def work(post, wh, sp, center=None, minutes=120, name='Mixing', scheduled='2026-06-01'):
    center = center or post('work_center', {'name': name, 'location': wh.location_id, 'daily_minutes': '240'}).result['work_center']
    item = post('work_order', {'work_center': center, 'warehouse': wh.id, 'product': sp.id, 'scheduled_date': scheduled, 'planned_minutes': str(minutes), 'planned_quantity': '100'})
    return center, item.result['work_order']


def test_multistage_capacity_wait_delivery_and_replanning_preserve_history(growth_env):
    ctx, post, wh, sp, *_ = growth_env
    mixing, target = work(post, wh, sp, minutes=180)
    cutting, other = work(post, wh, sp, name='Cutting', scheduled='2026-06-03', minutes=240)
    payload = {'work_order': target, 'earliest_date': '2026-06-01', 'requested_date': '2026-06-04', 'delivery_days': '1',
               'stages': [{'work_center': mixing, 'name': 'Mix', 'minutes': '60', 'wait_days': '0'}, {'work_center': cutting, 'name': 'Cut', 'minutes': '120', 'wait_days': '1'}]}
    before = Document.objects.count(); result = preview_schedule(ctx, payload)
    assert Document.objects.count() == before and not result['reserved']
    assert result['slots'][0]['date'] == '2026-06-01'
    assert result['finish_date'] == '2026-06-04' and result['delivery_date'] == '2026-06-05' and result['on_time'] is False
    posted = post('capacity_schedule', payload)
    assert posted.result['reserved'] and not posted.entries.exists() and not posted.movements.exists()
    assert capacity_usage(ctx.business, mixing, __import__('datetime').date(2026, 6, 1)) == 60
    assert capacity_usage(ctx.business, cutting, __import__('datetime').date(2026, 6, 4)) == 120
    assert planning_board(ctx, {})['results'][0]['schedule']['id'] == posted.id
    revised = post('capacity_schedule', {**payload, 'earliest_date': '2026-06-07', 'requested_date': '2026-06-12'})
    assert revised.id != posted.id and Document.objects.get(pk=posted.id).result == posted.result
    assert capacity_usage(ctx.business, mixing, __import__('datetime').date(2026, 6, 1)) == 0
    assert len([d for d in Document.objects.filter(kind='capacity_schedule')]) == 2


def test_schedule_capacity_checks_ordinary_work_and_center_edits(growth_env):
    ctx, post, wh, sp, *_ = growth_env
    center, target = work(post, wh, sp, minutes=240)
    stages = [{'work_center': center, 'name': 'Full day', 'minutes': '240'}]
    post('capacity_schedule', {'work_order': target, 'earliest_date': '2026-06-02', 'stages': stages})
    with pytest.raises(ValidationError, match='insufficient daily capacity'):
        work(post, wh, sp, center=center, minutes=1, scheduled='2026-06-02')
    with pytest.raises(ValidationError, match='cannot be reduced'):
        post('work_center', {'name': 'Mixing', 'location': wh.location_id, 'daily_minutes': '239'})
    post('work_close', {'work_order': target, 'state': 'cancelled', 'reason': 'Order cancelled'})
    _, replacement = work(post, wh, sp, center=center, minutes=240, scheduled='2026-06-02')
    assert replacement != target


def test_schedule_rejects_incomplete_estimate_started_work_and_permissions(growth_env):
    ctx, post, wh, sp, *_ = growth_env
    center, target = work(post, wh, sp)
    payload = {'work_order': target, 'earliest_date': '2026-06-01', 'stages': [{'work_center': center, 'name': 'Mix', 'minutes': '119'}]}
    with pytest.raises(ValidationError, match='total the existing work order'): preview_schedule(ctx, payload)
    payload['stages'][0]['minutes'] = '120'
    with pytest.raises(ValidationError, match='Insufficient capacity'):
        preview_schedule(ctx, {**payload, 'working_weekdays': [6], 'horizon_days': '1'})
    post('production_start', {'warehouse': wh.id, 'work_order': target})
    with pytest.raises(ValidationError, match='WIP batch'): post('capacity_schedule', payload)
    member = ctx.membership; member.permissions = ['production.view']; member.save()
    client = client_for(ctx.user, ctx.business)
    assert client.post('/api/planning/preview/', payload, content_type='application/json').status_code == 403
    member.all_locations = False; member.location_ids = []; member.save()
    assert client.get('/api/planning/board/').json()['results'] == []


def test_measured_yield_uses_original_geometry_and_net_inputs_without_required_formula(growth_env):
    ctx, post, wh, sp, raw, *_ = growth_env
    top = Product.objects.create(business=ctx.business, code='TOP', name='Top grade45', kind='trim', line='sponge', unit='each')
    post('stock_opening', {'warehouse': wh.id, 'lines': [{'product': raw.id, 'quantity': '100', 'value': '1000'}]})
    batch = post('production_start', {'warehouse': wh.id})
    consumed = post('production_consume', {'batch': batch.id, 'inputs': [{'product': raw.id, 'quantity': '10'}]})
    post('production_material_return', {'consumption': consumed.id, 'lines': [{'index': 0, 'quantity': '2'}]})
    completed = post('production_complete', {'batch': batch.id, 'outputs': [{'product': sp.id, 'blocks': [{'length_mm': '2000', 'width_mm': '1000', 'height_mm': '1060'}]}]})
    block = Block.objects.get(batch=completed)
    post('trim', {'block': block.id, 'main_height_mm': '1000', 'top_height_mm': '30', 'bottom_height_mm': '20', 'loss_mm': '10',
                  'outputs': [{'product': top.id, 'quantity': '1', 'cost': '0'}]})
    row = efficiency(ctx, {})['results'][0]
    assert row['formula_required'] is False and row['inputs'][0]['quantity'] == '8'
    assert Decimal(row['total_cost']) == 80 and Decimal(row['wip_remaining']) == 0
    assert Decimal(row['outputs'][0]['quantity']) == 106 and Decimal(row['outputs'][0]['volume_m3']) == Decimal('2.12')
    assert row['trims'][0]['main_yield_percent'] == '94.34'
    assert row['trims'][0]['loss_percent'] == '0.943396' and row['trims'][0]['review_loss'] is None
    assert row['flagged_losses'] is None
    before = (Document.objects.count(), Entry.objects.count(), StockMovement.objects.count())
    reviewed = efficiency(ctx, {'loss_limit_percent': '0.9'})['results'][0]
    assert reviewed['flagged_losses'] == 1 and reviewed['trims'][0]['review_loss'] is True
    assert efficiency(ctx, {'loss_limit_percent': '1'})['results'][0]['flagged_losses'] == 0
    assert before == (Document.objects.count(), Entry.objects.count(), StockMovement.objects.count())
    with pytest.raises(ValidationError): efficiency(ctx, {'loss_limit_percent': '-0.1'})
    with pytest.raises(ValidationError): efficiency(ctx, {'loss_limit_percent': '100.1'})
    member = ctx.membership; member.permissions = ['production.view']; member.save()
    public = efficiency(Context(ctx.user, ctx.business), {})['results'][0]
    assert 'inputs' not in public and 'total_cost' not in public and len(public['outputs']) == 1


def test_cutting_alternatives_preserve_reusable_remnants_and_post_selected_strategy(growth_env):
    ctx, post, wh, sp, *_ = growth_env
    small = open_block(post, wh, sp, '250')
    large = open_block(post, wh, sp, '400')
    payload = {'warehouse': wh.id, 'product': sp.id, 'profile': small.profile, 'lines': [{'thickness_mm': '200', 'sheet_count': '1'}], 'reusable_remnant_mm': '100'}
    result = cutting_alternatives(ctx, payload)
    options = {row['strategy']: row for row in result['alternatives']}
    assert options['best_fit']['allocations'][0]['block'] == small.id
    assert options['preserve_remnants']['allocations'][0]['block'] == large.id
    assert options['best_fit']['small_remnant_mm'] == '50.000'
    assert options['preserve_remnants']['small_remnant_mm'] == '0'
    assert not Document.objects.filter(kind='cut_plan').exists()
    plan = post('cut_plan', {**payload, 'strategy': 'preserve_remnants'})
    assert plan.result['strategy'] == 'preserve_remnants'
    post('cut_execute', {'plan': plan.result['plan']})
    small.refresh_from_db(); large.refresh_from_db()
    assert small.remaining_height_mm == 250 and large.remaining_height_mm == 200


def test_planning_and_yield_reject_cross_business_references(growth_env):
    ctx, post, wh, sp, *_ = growth_env
    from erp.models import Business, WorkCenter, Location
    other = Business.objects.create(name='Other business', slug='other-capacity')
    location = Location.objects.create(business=other, code='OTHER', name='Other')
    center = WorkCenter.objects.create(business=other, name='Hidden center', location=location)
    _, target = work(post, wh, sp)
    with pytest.raises(ValidationError, match='this business'):
        preview_schedule(ctx, {'work_order': target, 'earliest_date': '2026-06-01', 'stages': [{'work_center': center.id, 'name': 'Invalid', 'minutes': '120'}]})
    assert client_for(ctx.user, ctx.business).post('/api/planning/preview/', [], content_type='application/json').status_code == 400


def test_yield_repeated_product_outputs_are_individual_measured_pieces(growth_env):
    ctx, post, wh, sp, raw, *_ = growth_env
    post('stock_opening', {'warehouse': wh.id, 'lines': [{'product': raw.id, 'quantity': '10', 'value': '100'}]})
    batch = post('production', {'warehouse': wh.id, 'inputs': [{'product': raw.id, 'quantity': '10'}], 'outputs': [
        {'product': sp.id, 'cost': '40', 'blocks': [{'length_mm': '2000', 'width_mm': '1000', 'height_mm': '100'}]},
        {'product': sp.id, 'cost': '60', 'blocks': [{'length_mm': '1000', 'width_mm': '1000', 'height_mm': '200'}]},
    ]})
    row = efficiency(ctx, {})['results'][0]
    assert row['id'] == batch.id and len(row['outputs']) == 2
    assert len({output['profile'] for output in row['outputs']}) == 2
    assert {Decimal(output['volume_m3']) for output in row['outputs']} == {Decimal('.2')}


def test_new_multiday_work_reserves_all_days_once_and_factory_can_start_it(growth_env):
    ctx, post, wh, sp, *_ = growth_env
    center = post('work_center', {'name': 'Long running', 'location': wh.location_id, 'daily_minutes': '120'}).result['work_center']
    payload = {'date': '2026-06-01', 'warehouse': wh.id, 'product': sp.id, 'planned_quantity': '100', 'planned_minutes': '300',
               'earliest_date': '2026-06-01', 'stages': [{'work_center': center, 'name': 'Mix and process', 'minutes': '300'}]}
    preview = preview_new_work(ctx, payload)
    assert [slot['minutes'] for slot in preview['slots']] == [120, 120, 60]
    assert not WorkOrder.objects.exists()
    scheduled = post('capacity_work_order', payload, 'new-multiday')
    retry = post('capacity_work_order', payload, 'new-multiday')
    assert scheduled.id == retry.id and WorkOrder.objects.count() == 1
    assert not scheduled.entries.exists() and not scheduled.movements.exists()
    assert capacity_usage(ctx.business, center, __import__('datetime').date(2026, 6, 2)) == 120
    with pytest.raises(ValidationError, match='insufficient daily capacity'):
        work(post, wh, sp, center=center, minutes=1, scheduled='2026-06-02')
    batch = post('production_start', {'warehouse': wh.id, 'work_order': scheduled.result['work_order']})
    assert batch.kind == 'production_start'
    with pytest.raises(ValidationError, match='WIP batch'):
        post('capacity_schedule', {**payload, 'work_order': scheduled.result['work_order']})


@pytest.mark.django_db(transaction=True)
def test_competing_capacity_reservations_do_not_overbook_a_center(growth_env):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import connections
    ctx, post, wh, sp, *_ = growth_env
    center = post('work_center', {'name': 'Constrained', 'location': wh.location_id, 'daily_minutes': '120'}).result['work_center']
    payload = {'date': '2026-06-01', 'warehouse': wh.id, 'product': sp.id, 'planned_quantity': '100', 'planned_minutes': '120',
               'earliest_date': '2026-06-01', 'horizon_days': '1', 'stages': [{'work_center': center, 'name': 'One day', 'minutes': '120'}]}
    barrier = Barrier(2)
    def compete(key):
        connections.close_all()
        try:
            contender = Context(ctx.user, ctx.business)
            barrier.wait(timeout=15)
            execute(contender, 'capacity_work_order', payload, key)
            return 'reserved'
        except ValidationError:
            return 'full'
        finally: connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(compete, ['capacity-a', 'capacity-b']))
    assert sorted(results) == ['full', 'reserved']
    assert WorkOrder.objects.count() == 1 and Document.objects.filter(kind='capacity_work_order').count() == 1
