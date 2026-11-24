import './daily-enhancements.css';
import './shortcut-copy';
import {useEffect,useRef,useState} from 'react';
import {useNavigate,useLocation} from 'react-router-dom';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {Bell,RefreshCw,Undo2,Save,Plus,Trash2,Keyboard} from 'lucide-react';
import {dailyShortcut} from './keyboard-shortcuts';
import {useResource,useScope,hasPermission} from './App';
import {api,money,number} from './api';
import type {Row} from './api';
import {formatCalendarDate} from './calendar';
import {Panel,Spinner,ErrorNotice,Field} from './ui';
import {l} from './localize';
import {operationLabels} from './workflows';

function useAttention(){const{businessId,locationId}=useScope();return useQuery({queryKey:['attention',businessId,locationId],queryFn:()=>api.get('/api/attention/'),refetchInterval:60000});}
export function AttentionBadge(){const q=useAttention();return q.data?.shown?<span className="attention-count" title={l('خبرهای مجاز نمایش‌شده')}>{q.data.shown}{q.data.more?'+':''}</span>:null;}
export function AttentionBell(){
 const q=useAttention();const navigate=useNavigate();const{businessId,locationId}=useScope();const[open,setOpen]=useState(false);const ref=useRef<HTMLDivElement>(null);const button=useRef<HTMLButtonElement>(null);
 useEffect(()=>setOpen(false),[businessId,locationId]);
 useEffect(()=>{if(!open)return;const close=(event:PointerEvent)=>{if(!ref.current?.contains(event.target as Node))setOpen(false);};const key=(event:KeyboardEvent)=>{if(event.key==='Escape'){setOpen(false);button.current?.focus();}};document.addEventListener('pointerdown',close);document.addEventListener('keydown',key);return()=>{document.removeEventListener('pointerdown',close);document.removeEventListener('keydown',key);};},[open]);
 return <div className="attention-bell" ref={ref}><button ref={button} className="icon-button" aria-label={l('خبرها و کارهای منتظر')} aria-expanded={open} onClick={()=>setOpen(!open)}><Bell size={19}/><AttentionBadge/></button>{open&&<section className="attention-popover" aria-label={l('خبرها و کارهای منتظر')}><header><strong>{l('نیازمند توجه')}</strong><button className="icon-button" aria-label={l('تازه‌سازی')} onClick={()=>q.refetch()}><RefreshCw size={15}/></button></header>{q.isLoading?<Spinner/>:q.isError?<ErrorNotice error={q.error}/>:<><p>{l('خبرهای اخیر مجاز؛ عدد نشان‌دهنده تمام شرکت یا پیام‌های نخوانده نیست.')}</p>{q.data?.shown? q.data.groups.map((group:Row)=><div key={group.key}><h3>{l(group.title)}</h3>{group.results.map((row:Row)=><button className="attention-item" key={row.id} onClick={()=>{setOpen(false);navigate(group.key==='system'?'/settings?section=security':group.key==='approvals'?'/settings?section=finance#approvals':`/documents/${row.id}?business=${businessId}`);}}><bdi>{row.number}</bdi><span>{row.party_name||l(operationLabels[row.kind]||row.kind)}</span><small>{formatCalendarDate(row.date)}{row.balance!==null&&row.balance!==undefined?' · '+money(row.balance):''}</small></button>)}</div>):<p>{l('در این صفحه خبر مجاز منتظر نیست.')}</p>}</>}</section>}</div>;
}

const eventNames:Record<string,string>={created:'ایجاد سند',posted:'ثبت نهایی',printed:'درخواست چاپ',approved:'تأییدشده',rejected:'ردشده',approval_requested:'درخواست تأیید',draft_edited:'ویرایش مسوده',draft_undo:'برگشت ویرایش مسوده',draft_discarded:'لغو مسوده'};
export function DocumentTimeline({id}:{id:number}){
 const q=useResource(`/api/documents/${id}/timeline/`);const{showDocument}=useScope();
 return <details className="document-timeline"><summary>{l('تاریخچه و رویدادهای مرتبط')}</summary>{q.isLoading?<Spinner/>:q.isError?<ErrorNotice error={q.error}/>:<><p>{l('فقط رویدادهای ثبت‌شده؛ درخواست چاپ به معنی تحویل کاغذ نیست.')}</p><ol>{q.data?.results?.map((event:Row)=><li key={event.id}><span className="timeline-dot"/><div><strong>{l(eventNames[event.kind]||operationLabels[event.kind]||event.kind)}</strong><small>{formatCalendarDate(event.at)} {event.actor?' · '+event.actor:''}</small><button className="text-link" onClick={()=>showDocument({id:event.document})}><bdi>{event.number}</bdi></button></div></li>)}</ol></>}</details>;
}

function Spark({points,valueKey='amount'}:{points:Row[],valueKey?:string}){
 const values=points.map(p=>Number(p[valueKey]));const low=Math.min(0,...values),high=Math.max(1,...values);const coordinates=values.map((v,i)=>`${(i/Math.max(1,values.length-1)*300).toFixed(2)},${(90-(v-low)/(high-low)*75).toFixed(2)}`).join(' ');
 return <svg className="trend-svg" viewBox="0 0 310 110" role="img" aria-label={l('روند ثبت‌شده')}><line x1="0" x2="300" y1="95" y2="95" stroke="#dbe5ed"/><polyline points={coordinates} fill="none" stroke="#07838d" strokeWidth="2.5"/>{points.map((point,i)=><circle key={point.date} cx={i/Math.max(1,values.length-1)*300} cy={90-(values[i]-low)/(high-low)*75} r="3" fill="#07838d"><title>{formatCalendarDate(point.date)}: {point[valueKey]}</title></circle>)}</svg>;
}
export function OwnerTrends(){
 const{business}=useScope();const allowed=hasPermission(business,'reports.view')&&hasPermission(business,'accounting.view')&&hasPermission(business,'cost.view');const[days,setDays]=useState('30');const q=useResource(`/api/trends/?days=${days}`,allowed);const[series,setSeries]=useState('');
 if(!allowed)return null;const production=q.data?.production?.find((r:Row)=>`${r.product}:${r.profile}`===series)||q.data?.production?.[0];
 return <section className="owner-trends"><header><h2>{l('روندهای واقعی کسب‌وکار')}</h2><select aria-label={l('دوره روند')} value={days} onChange={e=>setDays(e.target.value)}>{['7','30','90'].map(day=><option key={day} value={day}>{number(day)} {l('روز')}</option>)}</select></header>{q.isLoading?<Spinner/>:q.isError?<ErrorNotice error={q.error}/>:<div className="trend-grid"><Panel title="روند فروش خالص"><Spark points={q.data?.sales||[]}/><small>{l('فقط فروش ثبت‌شده، پس از برگشت‌ها')}</small></Panel><Panel title="روند ارزش موجودی"><Spark points={q.data?.inventory||[]}/><small>{l('ارزش تاریخی حساب‌های موجودی؛ تولید در جریان جدا است.')}</small></Panel><Panel title="عمر طلب مشتریان"><div className="aging-chart">{Object.entries(q.data?.aging||{}).map(([key,value])=><div key={key}><span>{l(({current:'جاری','1_30':'۱ تا ۳۰ روز','31_60':'۳۱ تا ۶۰ روز','61_90':'۶۱ تا ۹۰ روز',over_90:'بیشتر از ۹۰ روز'} as Row)[key])}</span><strong>{money(value)}</strong><meter value={Math.max(0,Number(value))} max={Math.max(1,...Object.values(q.data?.aging||{}).map(Number))}/></div>)}</div><small>{l('مانده واقعی بل‌ها تا تاریخ انتخاب‌شده')}</small></Panel><Panel title="خروجی اندازه‌شده تولید">{production?<><select aria-label={l('محصول و اندازه')} value={`${production.product}:${production.profile}`} onChange={e=>setSeries(e.target.value)}>{q.data?.production.map((r:Row)=><option key={`${r.product}:${r.profile}`} value={`${r.product}:${r.profile}`}>{r.name} · {r.profile} · {r.unit}</option>)}</select><Spark points={production.points} valueKey="quantity"/></>:<p>{l('در این دوره خروجی ثبت‌شده نیست.')}</p>}<small>{l('هر درجه، اندازه و واحد جدا است؛ کیلوگرام به سانتی‌متر تبدیل نمی‌شود.')}</small></Panel></div>}</section>;
}

function DraftField({field,value,onChange,catalog,documents,blocks}:{field:Row,value:any,onChange:(value:any)=>void,catalog:Row,documents:Row[],blocks:Row[]}){
 const resource=field.resource;const choices=resource==='documents'?documents:resource==='blocks'?blocks:catalog[resource]||[];
 if(field.type==='protected')return <div className="field"><span>{l(field.label)}</span><small>{l('پیوند سیستمی محفوظ است.')}</small></div>;
 if(field.type==='group')return <fieldset className="draft-field-group"><legend>{l(field.label)}</legend>{field.fields.map((child:Row)=><DraftField key={child.key} field={child} value={value?.[child.key]} onChange={v=>onChange({...value,[child.key]:v})} catalog={catalog} documents={documents} blocks={blocks}/>)}</fieldset>;
 if(field.type==='list')return <fieldset className="draft-field-group"><legend>{l(field.label)}</legend>{(value||[]).map((row:any,index:number)=><div className="draft-list-row" key={index}><DraftField field={field.items[index]||field.items[0]||{key:String(index),label:l('ردیف'),type:'group',fields:Object.keys(field.template||{}).map(key=>({key,label:key,type:key==='product'?'reference':'decimal',resource:'products'}))}} value={row} onChange={v=>onChange(value.map((r:any,i:number)=>i===index?v:r))} catalog={catalog} documents={documents} blocks={blocks}/><button className="icon-button danger" type="button" aria-label={l('حذف ردیف')} onClick={()=>onChange(value.filter((_:any,i:number)=>i!==index))}><Trash2 size={15}/></button></div>)}{field.template!==null&&<button type="button" className="text-link" onClick={()=>onChange([...(value||[]),structuredClone(field.template)])}><Plus size={15}/>{l('افزودن ردیف')}</button>}</fieldset>;
 return <Field field={{key:`draft-${field.key}`,label:field.label,type:field.type==='reference'?'select':field.type==='decimal'?'number':field.type,options:choices.map((row:Row)=>({value:row.id,label:row.name||row.number||row.code||String(row.id)}))}} value={value??''} onChange={onChange}/>;
}
export function StructuredDraftEditor({id,onClose,onSaved}:{id:number,onClose:()=>void,onSaved:()=>void}){
 const q=useResource(`/api/documents/${id}/fields/`);const{catalog,notify,businessId}=useScope();const[values,setValues]=useState<Row|null>(null);const[error,setError]=useState<any>();const[busy,setBusy]=useState(false);const[undoEvent,setUndoEvent]=useState<number>();const qc=useQueryClient();const docs=useResource('/api/documents/?limit=200');const stock=useResource('/api/stock/');
 useEffect(()=>{setValues(null);setUndoEvent(undefined);},[id,businessId]);
 if(q.isLoading)return <Spinner/>;if(q.isError)return <ErrorNotice error={q.error}/>;
 const data=values||q.data?.data||{};
 return <form className="structured-draft" onSubmit={async event=>{event.preventDefault();setBusy(true);setError(undefined);try{const result=await api.patch(`/api/documents/${id}/fields/`,{data,version:q.data?.version});setValues(result.data);setUndoEvent(result.undo_event);await q.refetch();qc.invalidateQueries({queryKey:[`/api/documents/${id}/`]});qc.invalidateQueries({queryKey:[`/api/documents/${id}/timeline/`]});notify('پیش‌نویس ذخیره شد.');onSaved();}catch(e){setError(e);}finally{setBusy(false);}}}><p className="form-info">{l('مسوده حساب‌ها یا موجودی را تغییر نمی‌دهد. پیش از ثبت نهایی، قواعد عادی دوباره بررسی می‌شوند.')}</p><div className="structured-fields">{q.data?.fields.map((field:Row)=><DraftField key={field.key} field={field} value={data[field.key]} onChange={v=>setValues({...data,[field.key]:v})} catalog={catalog} documents={docs.data?.results||[]} blocks={stock.data?.blocks||[]}/>)}</div>{error&&<ErrorNotice error={error}/>}<div className="action-row"><button type="submit" className="button primary" disabled={busy}><Save size={16}/>{l('ذخیره تغییرات')}</button><button type="button" className="button secondary" onClick={onClose}>{l('بستن')}</button>{undoEvent&&<button type="button" className="button secondary" disabled={busy} onClick={async()=>{setBusy(true);setError(undefined);try{const result=await api.post(`/api/documents/${id}/fields/`,{undo_event:undoEvent});setValues(result.data);setUndoEvent(undefined);await q.refetch();qc.invalidateQueries({queryKey:[`/api/documents/${id}/`]});qc.invalidateQueries({queryKey:[`/api/documents/${id}/timeline/`]});onSaved();}catch(e){setError(e);}finally{setBusy(false);}}}><Undo2 size={16}/>{l('برگشت آخرین ویرایش')}</button>}</div></form>;
}

export function DailyShortcuts(){
 const{perform,canAction}=useScope();const{pathname}=useLocation();const help=useRef<HTMLDetailsElement>(null);
 useEffect(()=>{if(help.current)help.current.open=false;},[pathname]);
 useEffect(()=>{
  const key=(event:KeyboardEvent)=>{
   if(event.key==='Escape'&&help.current?.open){help.current.open=false;help.current.querySelector('summary')?.focus();return;}
   if(document.querySelector('[role=dialog]'))return;
   const action=dailyShortcut(event,pathname);if(!action)return;
   if(action==='search'){
    const selectors=['.workspace .document-register .data-grid-search input','.workspace .data-grid-search input','.workspace input[type=search]','.workspace .global-search input'];
    const search=selectors.flatMap(selector=>Array.from(document.querySelectorAll<HTMLInputElement>(selector))).find(input=>!input.disabled&&input.getClientRects().length>0);
    if(search){event.preventDefault();search.focus();search.select();if(help.current)help.current.open=false;}
   }else if(canAction(action)){event.preventDefault();if(help.current)help.current.open=false;perform(action);}
  };
  const outside=(event:PointerEvent)=>{if(help.current?.open&&!help.current.contains(event.target as Node))help.current.open=false;};
  window.addEventListener('keydown',key);document.addEventListener('pointerdown',outside);
  return()=>{window.removeEventListener('keydown',key);document.removeEventListener('pointerdown',outside);};
 },[pathname,perform,canAction]);
 return pathname==='/purchases'||pathname==='/transfers'?<div className="shortcut-hints"><details className="shortcut-help" ref={help}><summary><Keyboard size={17}/>{l('میانبرهای صفحه‌کلید')}</summary><div className="shortcut-help-panel"><strong>{l('میانبرهای صفحه‌کلید')}</strong><dl><div><dt><kbd dir="ltr">Ctrl+K</kbd> / <kbd dir="ltr">Alt+F</kbd></dt><dd>{l('جستجو در همین صفحه')}</dd></div>{canAction(pathname==='/purchases'?'purchase_receive':'transfer_dispatch')&&<div><dt><kbd dir="ltr">Alt+N</kbd></dt><dd>{l('ثبت جدید')}</dd></div>}{canAction(pathname==='/purchases'?'supplier_payment':'transfer_receive')&&<div><dt><kbd dir="ltr">Alt+R</kbd></dt><dd>{l(pathname==='/purchases'?'پرداخت تأمین‌کننده':'تأیید دریافت')}</dd></div>}</dl><small>{l('میانبرها هنگام باز بودن فورم فعال نیستند.')}</small></div></details></div>:null;
}
