from datetime import date,timedelta
import jdatetime
from django.core.exceptions import ValidationError
from .api import Boundary,response
from .models import UserPreference
from django.db import transaction

AFGHAN_MONTHS=['حمل','ثور','جوزا','سرطان','اسد','سنبله','میزان','عقرب','قوس','جدی','دلو','حوت']

def calendar_month(year,month):
    try:
        year=int(year);month=int(month)
        first=jdatetime.date(year,month,1).togregorian()
        following=jdatetime.date(year+1,1,1).togregorian() if month==12 else jdatetime.date(year,month+1,1).togregorian()
        if first.year<1900 or first.year>2200:raise ValueError()
    except (ValueError,TypeError,OverflowError):raise ValidationError('Select a valid Jalali month within the supported date range.')
    start=first-timedelta(days=(first.weekday()+2)%7)
    cells=[]
    for offset in range(42):
        day=start+timedelta(days=offset);jalali=jdatetime.date.fromgregorian(date=day)
        cells.append({'gregorian':day.isoformat(),'jalali':f'{jalali.year:04}-{jalali.month:02}-{jalali.day:02}','day':jalali.day,'in_month':jalali.month==month and jalali.year==year,'selectable':1900<=day.year<=2200})
    return {'year':year,'month':month,'month_name':AFGHAN_MONTHS[month-1],'month_names':AFGHAN_MONTHS,'first':first.isoformat(),'last':(following-timedelta(days=1)).isoformat(),'days':cells,'week_starts':'Saturday'}

def convert_calendar(value,source):
    value=str(value).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789')).replace('/','-')
    try:
        parts=list(map(int,value.split('-')))
        if len(parts)!=3:raise ValueError()
        if source=='jalali':
            jalali=jdatetime.date(*parts);gregorian=jalali.togregorian()
        elif source=='gregorian':
            gregorian=date(*parts);jalali=jdatetime.date.fromgregorian(date=gregorian)
        else:raise ValueError()
        if not 1900<=gregorian.year<=2200:raise ValueError()
    except (ValueError,TypeError,OverflowError):raise ValidationError('Enter a real date between Gregorian years 1900 and 2200.')
    return {'gregorian':gregorian.isoformat(),'jalali':f'{jalali.year:04}-{jalali.month:02}-{jalali.day:02}','canonical_calendar':'gregorian'}

def printed_date(value,user):
    preference=UserPreference.objects.filter(user=user).first()
    if preference and preference.calendar=='gregorian':return value.isoformat()
    return convert_calendar(value.isoformat(),'gregorian')['jalali']+' (هجری شمسی / Jalali)'

class CalendarAPI(Boundary):
    def get(self,request):
        if request.query_params.get('view')=='month':return response(calendar_month(request.query_params.get('year'),request.query_params.get('month')))
        if request.query_params.get('view')=='period':
            from .calendar_periods import period_data
            return response(period_data(request.query_params.get('value'),request.query_params.get('calendar','gregorian')))
        return response(convert_calendar(request.query_params.get('value'),request.query_params.get('from','gregorian')))

class PreferenceAPI(Boundary):
    def get(self,request):
        item,_=UserPreference.objects.get_or_create(user=request.user)
        return response({'language':item.language,'calendar':item.calendar})
    @transaction.atomic
    def patch(self,request):
        if set(request.data)-{'language','calendar'}:raise ValidationError('Unknown preference.')
        item,_=UserPreference.objects.select_for_update().get_or_create(user=request.user)
        for key,value in request.data.items():setattr(item,key,value)
        item.full_clean();item.save(update_fields=list(request.data))
        return response({'language':item.language,'calendar':item.calendar})
