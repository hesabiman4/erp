import './order-readiness-copy';
import './order-readiness.css';
import {useState} from 'react';
import {useQueryClient} from '@tanstack/react-query';
import {useScope,useResource,hasPermission} from './App';
import {api,number,today} from './api';
import type {Row} from './api';
import {Field,Panel,Spinner,ErrorNotice,SimpleForm} from './ui';
import {l} from './localize';
import {formatCalendarDate} from './calendar';

const statuses:Record<string,string>={inactive_product:'محصول غیرفعال',ready_now:'آماده در همین انبار',shortage:'کمبود موجودی مناسب',needs_cut_details:'اندازه و ضخامت برش را مشخص کنید',quality_hold:'توقف کیفیت محصول',service_review:'خدمت؛ نیازمند بررسی مسؤول',fulfilled:'تکمیل شده',closed:'بسته‌شده'};
export function OrderReadiness({document:d}:{document:Row}){
 const{business}=useScope();const[open,setOpen]=useState(false);
 if(d.kind!=='sales_order'||d.state!=='posted'||!hasPermission(business,'inventory.view','sales.post'))return null;
 return <section className="order-readiness"><button className="button secondary" aria-expanded={open} onClick={()=>setOpen(!open)}>{l('بررسی آمادگی سفارش و وعده تحویل')}</button>{open&&<ReadinessState key={d.id} document={d}/>}</section>;
}
function ReadinessState({document:d}:{document:Row}){
 const{business,showDocument}=useScope();const qc=useQueryClient();const[inputs,setInputs]=useState<Row>({});const[applied,setApplied]=useState<Row>({});const[promising,setPromising]=useState(false);
 const params=new URLSearchParams(applied);const path=`/api/orders/${d.id}/readiness/?${params}`;const q=useResource(path);
 return <div className="readiness-body"><p className="form-info">{l('این بررسی رزرو یا فروش نیست. موجودی هنگام برش یا بل‌کردن دوباره بررسی می‌شود؛ تاریخ تولید به تنهایی تضمین تحویل نیست.')}</p>
  {q.isLoading?<Spinner/>:q.isError?<ErrorNotice error={q.error} retry={()=>q.refetch()}/>:q.data&&<>
   <div className="readiness-header"><h3>{l('آمادگی سفارش')} · {q.data.warehouse_name}</h3><strong>{l(q.data.closed?'بسته‌شده':q.data.ready_now?'تمام اقلام آماده است':'موارد نیازمند بررسی دارد')}</strong><button className="button secondary small" disabled={q.isFetching} onClick={()=>{if(JSON.stringify(inputs)===JSON.stringify(applied))q.refetch();else setApplied({...inputs});}}>{l('بررسی دوباره')}</button></div>
   <div className="readiness-lines">{q.data.lines.map((row:Row)=><article key={row.index}><header><h4>{row.product_name}</h4><strong>{l(statuses[row.status]||row.status)}</strong></header><dl><div><dt>{l('مانده سفارش')}</dt><dd><bdi>{number(row.remaining,6)} {row.unit}</bdi></dd></div><div><dt>{l('قابل تهیه در این بررسی')}</dt><dd><bdi>{number(row.available,6)} {row.unit}</bdi></dd></div><div><dt>{l('کمبود')}</dt><dd><bdi>{number(row.shortage,6)} {row.unit}</bdi></dd></div></dl>
    {row.unit==='cm'&&Number(row.remaining)>0&&<><p><span>{l('اندازه / مشخصه')}: </span><bdi>{row.profile||l('در سفارش مشخص نشده')}</bdi></p>{row.profile&&<div className="form-grid"><Field field={{key:`thickness_${row.index}`,label:'ضخامت مورد نیاز هر ورق (mm)',type:'number'}} value={inputs[`thickness_${row.index}`]||''} onChange={value=>setInputs({...inputs,[`thickness_${row.index}`]:value})}/><Field field={{key:`loss_${row.index}`,label:'ضایعات برش هر ورق (mm)',type:'number'}} value={inputs[`loss_${row.index}`]||'0'} onChange={value=>setInputs({...inputs,[`loss_${row.index}`]:value})}/></div>}<p className="ledger-note">{l('مانده باید با تعداد صحیح ورق سازگار باشد. قطعات کوچک برای ساختن یک ورق ضخیم به هم جمع نمی‌شوند.')}</p></>}
    {row.allocations?.length>0&&<ul className="readiness-allocations">{row.allocations.map((a:Row)=><li key={a.block}><bdi>{a.code}</bdi> · {number(a.sheets)} {l('ورق')}{a.held_for_this_order&&<> · {l('قبلاً برای همین سفارش برش شده')}</>}</li>)}</ul>}
   </article>)}</div>
   {q.data.work.length>0&&<Panel title="تولید برنامه‌شده مرتبط"><p>{l('این تاریخ برنامه است؛ تأیید کیفیت، برش، بارگیری و تحویل باید جدا بررسی شود.')}</p>{q.data.work.map((w:Row)=><div className="readiness-work" key={w.id}><bdi>{w.number}</bdi><span>{w.product_name}</span><span>{number(w.planned_quantity,6)} {w.unit}</span><strong>{w.scheduled_through?formatCalendarDate(w.scheduled_through):'—'}</strong></div>)}</Panel>}
   <Panel title="وعده‌های تحویل بررسی‌شده"><p>{l('وعده تازه سابقه قبلی را حذف نمی‌کند و موجودی را رزرو نمی‌کند.')}</p>{q.data.promises.map((p:Row,index:number)=><article className="order-promise" key={p.document}><header><strong>{formatCalendarDate(p.promised_date)}</strong><span>{l(index===0?'آخرین وعده ثبت‌شده':'وعده قبلی')}</span><button className="text-link" onClick={()=>showDocument({id:p.document})}><bdi>{p.number}</bdi></button></header><p>{p.reason}</p><p><strong>{l('مبنای وعده')}: </strong>{p.basis}</p></article>)}{hasPermission(business,'sales.promise')&&!q.data.closed&&<button className="button secondary" onClick={()=>setPromising(!promising)}>{l('ثبت وعده تحویل')}</button>}
    {promising&&<SimpleForm fields={[{key:'date',label:'تاریخ سند',type:'date',default:today(),required:true},{key:'promised_date',label:'تاریخ وعده تحویل',type:'date',required:true},{key:'basis',label:'مبنای وعده',type:'textarea',required:true,span:true,help:'موجودی مناسب، برنامه تولید، کیفیت، برش و حمل را با مسؤول مربوط بررسی کنید.'},{key:'reason',label:'دلیل / توافق با مشتری',type:'textarea',required:true,span:true}]} onSubmit={async values=>{await api.post('/api/operations/order_promise/',{...values,order:d.id});setPromising(false);qc.invalidateQueries({queryKey:[path]});}}/>}
   </Panel>
  </>}
 </div>;
}
