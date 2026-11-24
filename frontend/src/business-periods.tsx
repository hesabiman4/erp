import {l} from './localize';
import './planning-help-copy';
import {useRef,useState} from 'react';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {useTranslation} from 'react-i18next';
import {hasPermission,useResource,useScope} from './App';
import {api,today} from './api';
import type {Row} from './api';
import {formatCalendarDate} from './calendar';
import type {CalendarMode} from './calendar';
import {DataTable,ErrorNotice,Field,Panel,Spinner} from './ui';
import type {FieldDef} from './ui';

const afghanMonths=['حمل','ثور','جوزا','سرطان','اسد','سنبله','میزان','عقرب','قوس','جدی','دلو','حوت'];
export function businessCalendar(settings:Row,day:string):CalendarMode{
 const policy=(settings?.calendar_policies||[]).filter((p:Row)=>p.effective_from<=day).at(-1);
 return policy?.calendar==='jalali'?'jalali':'gregorian';
}
export function businessPeriodFor(day:string,calendar:CalendarMode){
 if(calendar==='gregorian')return day.slice(0,7);
 const parts=new Intl.DateTimeFormat('en-US-u-ca-persian',{year:'numeric',month:'2-digit',timeZone:'Asia/Kabul'}).formatToParts(new Date(day+'T12:00:00Z'));
 return `${parts.find(p=>p.type==='year')?.value}-${parts.find(p=>p.type==='month')?.value}`;
}
export function BusinessPeriodInput({value,calendar,onChange,label}:{value:string,calendar:CalendarMode,onChange:(value:string)=>void,label?:string}){
 const{i18n}=useTranslation();const en=i18n.language==='en';const year=Number((value||businessPeriodFor(today(),calendar)).slice(0,4));const current=Number(businessPeriodFor(today(),calendar).slice(0,4));
 const q=useQuery({queryKey:['explicit-calendar-period',calendar,value],queryFn:()=>api.get(`/api/calendar/?view=period&calendar=${calendar}&value=${encodeURIComponent(value)}`),enabled:!!value});
 const years=Array.from({length:Math.max(current+4,year)-Math.min(current-5,year)+1},(_,i)=>Math.min(current-5,year)+i).reverse();
 const options=years.flatMap(y=>Array.from({length:12},(_,i)=>({value:`${y}-${String(i+1).padStart(2,'0')}`,label:`${y} · ${calendar==='jalali'?l(afghanMonths[i]):new Intl.DateTimeFormat(en?'en-US':i18n.language==='ps'?'ps-AF':'fa-AF',{calendar:'gregory',month:'long'}).format(new Date(Date.UTC(2026,i,15)))}`})));
 return <div><Field field={{key:'business_month',label:label||(en?'Earning month':l('ماه معاش')),type:'select',required:true,options}} value={value} onChange={onChange}/>{q.data&&<small className="ledger-note" data-period-boundaries>{formatCalendarDate(q.data.first)} — {formatCalendarDate(q.data.last)} · {q.data.days} {en?'calendar days':l('روز تقویمی')}</small>}{q.isError&&<ErrorNotice error={q.error}/>}</div>;
}

export function BusinessPeriodsWorkspace(){
 const{business,businessId,catalog,notify}=useScope();const{i18n}=useTranslation();const en=i18n.language==='en';const tx=(fa:string,english:string)=>en?english:l(fa);const qc=useQueryClient();
 const q=useResource('/api/business-periods/');const[calendar,setCalendar]=useState<CalendarMode>('jalali');const[effective,setEffective]=useState('');const[reason,setReason]=useState('');const[error,setError]=useState('');const[busy,setBusy]=useState(false);const requestKey=useRef({body:'',key:''});
 const can=hasPermission(business,'settings.manage')&&hasPermission(business,'accounting.manage');
 return <>{q.isLoading?<Spinner/>:q.isError?<ErrorNotice error={q.error}/>:<Panel title={tx('تقویم کاری و دوره‌های واقعی','Business calendar and actual periods')} subtitle={tx('تقویم نمایشی با تقویم محاسبه معاش فرق دارد. تغییر دوره، تاریخچه را دوباره محاسبه نمی‌کند.','Display preferences and contractual earning periods are separate. Policy changes never recalculate posted history.')}><div className="form-info"><strong>{tx('تقویم فعلی کسب‌وکار:','Current business calendar: ')}{q.data?.active_calendar==='jalali'?tx('هجری شمسی','Jalali'):tx('میلادی','Gregorian')}</strong><p>{tx('روزهای دفتر حساب همیشه با تاریخ اصلی ذخیره می‌شوند. دوره شمسی، معاش و بودجه را با مرز واقعی ماه شمسی محاسبه می‌کند.','Ledger dates retain their canonical values. Jalali earning and budget months use their actual month boundaries.')}</p></div><DataTable data={q.data?.policies||[]} columns={[{key:'calendar',label:tx('تقویم','Calendar'),render:r=>r.calendar==='jalali'?tx('هجری شمسی','Jalali'):tx('میلادی','Gregorian')},{key:'effective_from',label:tx('آغاز اجرا','Effective from')},{key:'reason',label:tx('دلیل / مرور','Review reason')}]}/></Panel>}
 {can&&<Panel title={tx('تغییر تقویم با تاریخ اجرا','Schedule a calendar change')}><form onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{const payload={date:today(),calendar,effective_from:effective,reason};const body=JSON.stringify(payload);if(requestKey.current.body!==body)requestKey.current={body,key:crypto.randomUUID()};await api.post('/api/operations/calendar_policy/',payload,requestKey.current.key);await qc.invalidateQueries();setReason('');notify(tx('تقویم کاری با تاریخ اجرا ثبت شد.','Business calendar policy scheduled.'));}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}}><div className="form-grid"><Field field={{key:'policy_calendar',label:tx('تقویم جدید','New calendar'),type:'select',required:true,options:[{value:'jalali',label:tx('هجری شمسی','Jalali')},{value:'gregorian',label:tx('میلادی','Gregorian')}]}} value={calendar} onChange={setCalendar}/><Field field={{key:'effective_from',label:tx('نخستین روز ماه جدید','First day of the new calendar month'),type:'date',required:true}} value={effective} onChange={setEffective}/><Field field={{key:'calendar_reason',label:tx('دلیل و مرور تغییر','Reason and transition review'),type:'textarea',required:true,span:true}} value={reason} onChange={setReason}/></div><p className="form-info">{tx('تغییر فقط برای آینده است. ماه آخر تقویم قبلی تا روز پیش از آغاز تقویم جدید کوتاه و به نسبت روزها محاسبه می‌شود؛ معاش ثبت‌شده تغییر نمی‌کند. پیش از اجرا قراردادها و دوره انتقال را مرور کنید.','Changes are prospective. The last old-calendar month ends the day before the new calendar starts and is prorated against its original full month. Review employment terms and the transition before scheduling.')}</p>{error&&<ErrorNotice error={error}/>}<footer className="form-footer"><span>{catalog.business?.name||businessId}</span><button className="button primary" type="submit" disabled={busy}>{tx('ثبت تاریخ اجرا','Schedule change')}</button></footer></form></Panel>}
 <CalendarReportPreview/>
 </>;
}

function CalendarReportPreview(){
 const{i18n}=useTranslation();const en=i18n.language==='en';const{catalog}=useScope();const[calendar,setCalendar]=useState<CalendarMode>(()=>businessCalendar(catalog.business?.settings,today()));const[period,setPeriod]=useState(()=>businessPeriodFor(today(),calendar));
 const q=useResource(`/api/business-periods/?calendar=${calendar}&period=${period}`);
 return <Panel title={en?'Review exact month boundaries':l('مرور مرز واقعی ماه')}><div className="form-grid"><Field field={{key:'preview_calendar',label:en?'Period calendar':l('تقویم دوره'),type:'select',options:[{value:'jalali',label:'هجری شمسی / Jalali'},{value:'gregorian',label:'میلادی / Gregorian'}]}} value={calendar} onChange={c=>{setCalendar(c);setPeriod(businessPeriodFor(today(),c));}}/><BusinessPeriodInput calendar={calendar} value={period} onChange={setPeriod}/></div>{q.data&&<p className="form-info">{q.data.earning_window?.valid?`${en?'Contractual earning window':l('دوره واقعی معاش')}: ${formatCalendarDate(q.data.earning_window.first)} — ${formatCalendarDate(q.data.earning_window.last)}`:q.data.earning_window?.error}</p>}{q.isError&&<ErrorNotice error={q.error}/>}</Panel>;
}

export function BudgetCalendarForm({initial={},submit}:{initial?:Row,submit:(payload:Row)=>Promise<void>}){
 const{catalog}=useScope();const{i18n}=useTranslation();const en=i18n.language==='en';const calendar=businessCalendar(catalog.business?.settings,today());const[v,setV]=useState<Row>({date:today(),period_calendar:calendar,period:businessPeriodFor(today(),calendar),account:'',location:'',line:'shared',amount:'',...initial});const[busy,setBusy]=useState(false);const[error,setError]=useState('');
 const fields:FieldDef[]=[{key:'date',label:en?'Posting date':l('تاریخ ثبت'),type:'date',required:true},{key:'period_calendar',label:en?'Budget calendar':l('تقویم بودجه'),type:'select',required:true,options:[{value:'jalali',label:'هجری شمسی / Jalali'},{value:'gregorian',label:'میلادی / Gregorian'}]},{key:'account',label:en?'Budget account':l('حساب بودجه'),type:'select',required:true,options:(catalog.accounts||[]).filter((a:Row)=>['income','expense'].includes(a.category)).map((a:Row)=>({value:a.id,label:a.name}))},{key:'location',label:en?'Location':l('موقعیت'),type:'select',required:true,options:(catalog.locations||[]).map((a:Row)=>({value:a.id,label:a.name}))},{key:'line',label:en?'Product line':l('خط محصول'),type:'select',required:true,options:[{value:'sponge',label:en?'Sponge':l('اسفنج')},{value:'adhesive',label:en?'Adhesive':l('چسپ')},{value:'shared',label:en?'Shared':l('عمومی')}]},{key:'amount',label:en?'Budget amount (AFN)':l('بودجه (AFN)'),type:'number',required:true}];
 return <form onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{await submit(v);}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}}><div className="form-grid">{fields.slice(0,2).map(f=><Field key={f.key} field={f} value={v[f.key]} onChange={value=>setV({...v,[f.key]:value,...(f.key==='period_calendar'?{period:businessPeriodFor(today(),value)}:{})})}/>)}<BusinessPeriodInput calendar={v.period_calendar} value={v.period} onChange={period=>setV({...v,period})} label={en?'Budget month':l('ماه بودجه')}/>{fields.slice(2).map(f=><Field key={f.key} field={f} value={v[f.key]} onChange={value=>setV({...v,[f.key]:value})}/>)}</div>{error&&<ErrorNotice error={error}/>}<footer className="form-footer"><span>{en?'Planning only; no journal is posted.':l('فقط برنامه است؛ سند حسابداری ایجاد نمی‌شود.')}</span><button className="button primary" type="submit" disabled={busy}>{en?'Save budget':l('ثبت بودجه')}</button></footer></form>;
}
