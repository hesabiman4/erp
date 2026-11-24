"""Explicit business earning calendars; canonical ledger dates remain Gregorian.

Calendar preferences only control presentation. A prospective, append-only policy
controls earning windows; posted documents retain their original exact bounds.
"""
from calendar import monthrange
from datetime import date, timedelta
import re

import jdatetime
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from .models import Document

CALENDARS = {'gregorian', 'jalali'}
AFGHAN_MONTHS = ['حمل','ثور','جوزا','سرطان','اسد','سنبله','میزان','عقرب','قوس','جدی','دلو','حوت']


def iso_day(value):
    try:
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    except (ValueError, TypeError):
        raise ValidationError('Enter a valid canonical YYYY-MM-DD date.')


def month_bounds(period, calendar='gregorian'):
    if calendar not in CALENDARS:
        raise ValidationError('Select gregorian or jalali as the period calendar.')
    value = str(period).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))
    if not re.fullmatch(r'\d{4}-\d{2}', value):
        raise ValidationError('Period must use YYYY-MM in the selected calendar.')
    year, month = map(int, value.split('-'))
    try:
        if calendar == 'jalali':
            first = jdatetime.date(year, month, 1).togregorian()
            following = jdatetime.date(year + 1, 1, 1) if month == 12 else jdatetime.date(year, month + 1, 1)
            last = following.togregorian() - timedelta(days=1)
        else:
            first, last = date(year, month, 1), date(year, month, monthrange(year, month)[1])
        if not 1900 <= first.year <= 2199 or last.year > 2200:
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        raise ValidationError('Select a real month within Gregorian years 1900–2199.')
    return first, last


def period_for(day, calendar='gregorian'):
    day = iso_day(day)
    if calendar not in CALENDARS:
        raise ValidationError('Select gregorian or jalali as the period calendar.')
    value = jdatetime.date.fromgregorian(date=day) if calendar == 'jalali' else day
    return f'{value.year:04}-{value.month:02}'


def period_data(period, calendar='gregorian'):
    first, last = month_bounds(period, calendar)
    normalized = period_for(first, calendar)
    return {'calendar': calendar, 'period': normalized, 'key': f'{calendar}:{normalized}',
            'first': first.isoformat(), 'last': last.isoformat(), 'days': (last-first).days+1,
            'month_name': AFGHAN_MONTHS[int(normalized[-2:])-1] if calendar == 'jalali' else first.strftime('%B'),
            'canonical_calendar': 'gregorian'}


def policies(business):
    """The baseline never changes retroactively for an existing installation."""
    return [{'calendar': 'gregorian', 'effective_from': '1900-01-01', 'source': None},
            *business.settings.get('calendar_policies', [])]


def policy_at(business, day):
    day = iso_day(day)
    matching = [item for item in policies(business) if iso_day(item['effective_from']) <= day]
    return matching[-1]


def earning_month(business, period, calendar='gregorian'):
    """Clip the final old-calendar month at a prospective policy transition.

    The contractual monthly denominator remains the full original calendar month,
    so a transition segment is prorated rather than paid as an extra full month.
    """
    first, last = month_bounds(period, calendar)
    if policy_at(business, first)['calendar'] != calendar:
        raise ValidationError('This earning month does not use the configured business calendar. Select its approved calendar.')
    full_last = last
    following = [iso_day(item['effective_from']) for item in policies(business) if first < iso_day(item['effective_from']) <= last]
    if following:
        last = min(following) - timedelta(days=1)
    return first, last, (full_last-first).days+1


def calendar_policy(ctx, payload, doc):
    """Audited configuration event, no journals or physical movements."""
    ctx.require('accounting.manage')
    if not ctx.membership.all_locations or not {'sponge','adhesive','shared'}.issubset(ctx.membership.product_lines):
        raise PermissionDenied('Business calendar changes require full business scope.')
    calendar = payload.get('calendar')
    if calendar not in CALENDARS:
        raise ValidationError('Select gregorian or jalali.')
    effective = iso_day(payload.get('effective_from'))
    first, _ = month_bounds(period_for(effective, calendar), calendar)
    if effective != first:
        raise ValidationError('A calendar change must start on the first day of its new calendar month.')
    if effective < timezone.localdate() or effective < doc.date:
        raise ValidationError('Calendar policy changes must be prospective; historical earning periods are preserved.')
    reason = str(payload.get('reason') or '').strip()
    if len(reason) < 8:
        raise ValidationError('Document the reason and review of the calendar transition.')
    history = list(ctx.business.settings.get('calendar_policies', []))
    if history and effective <= iso_day(history[-1]['effective_from']):
        raise ValidationError('Append a later effective date; existing calendar policies are immutable.')
    if policy_at(ctx.business, effective)['calendar'] == calendar:
        raise ValidationError('This calendar is already configured for that date.')
    for payroll in Document.objects.filter(business=ctx.business, kind='payroll_accrue', state='posted'):
        from .finance import _payroll_window
        start, end = _payroll_window(payroll)
        if end >= effective:
            raise ValidationError('The change overlaps already accrued payroll. Select a later effective month.')
    history.append({'calendar': calendar, 'effective_from': effective.isoformat(), 'source': doc.pk,
                    'reason': reason, 'by': ctx.user.pk})
    ctx.business.settings = {**ctx.business.settings, 'calendar_policies': history}
    ctx.business.save(update_fields=['settings'])
    return {'calendar': calendar, 'effective_from': effective.isoformat(), 'previous_calendar': policy_at(ctx.business, effective-timedelta(days=1))['calendar'],
            'history_preserved': True, 'financial_posting': False}


def registry():
    return {'calendar_policy': ('settings.manage', calendar_policy)}


def workspace(ctx, params):
    if not any(ctx.has(permission) for permission in ('accounting.view','accounting.manage','payroll.view','payroll.post','settings.manage')):
        raise PermissionDenied('Business calendar access requires payroll, accounting or settings permission.')
    reference = iso_day(params.get('for_date') or timezone.localdate())
    active = policy_at(ctx.business, reference)
    calendar = params.get('calendar') or active['calendar']
    period = params.get('period') or period_for(reference, calendar)
    result = period_data(period, calendar)
    try:
        first, last, denominator = earning_month(ctx.business, period, calendar)
        earning = {'first': first.isoformat(), 'last': last.isoformat(), 'denominator_days': denominator, 'valid': True}
    except ValidationError as exc:
        earning = {'valid': False, 'error': '; '.join(exc.messages)}
    return {'active_calendar': active['calendar'], 'active_policy': active, 'policies': policies(ctx.business),
            'period': result, 'earning_window': earning,
            'note': 'Calendar display preferences do not change contracts. Ledger dates remain Gregorian; periods use explicit exact boundaries.'}


from .api import Boundary, response


class BusinessPeriodsAPI(Boundary):
    def get(self, request):
        return response(workspace(self.ctx(request), dict(request.query_params.items())))
