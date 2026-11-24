import './factory-review-copy';
import './factory-review.css';
import {useState} from 'react';
import {useScope,useResource} from './App';
import {today,money,number} from './api';
import {CalendarInput} from './calendar';
import {Panel,DataTable,Spinner,ErrorNotice} from './ui';
import type {Column} from './ui';
import {l} from './localize';

export function FactoryReviewPanel(){const{businessId,locationId}=useScope();return <ReviewState key={businessId+':'+locationId}/>;}
function ReviewState(){
 const[open,setOpen]=useState(false);const[from,setFrom]=useState(today());const[to,setTo]=useState(today());const[period,setPeriod]=useState({from:today(),to:today()});
 const q=useResource(`/api/factory-review/?from=${period.from}&to=${period.to}`,open);const d=q.data;
 const stockColumns:Column[]=[{key:'product_name',label:'محصول'},{key:'warehouse_name',label:'انبار'},{key:'profile',label:'اندازه / مشخصه'},{key:'quantity',label:'مقدار',sortType:'decimal',render:r=><bdi>{number(r.quantity,6)} {r.unit}</bdi>},{key:'blocks',label:'تعداد بلوک تولیدشده',render:r=>r.unit==='cm'?number(r.blocks):'—'}];
 if(d?.costs)stockColumns.push({key:'carrying_value',label:'ارزش دفتری',sortType:'decimal',render:r=>money(r.carrying_value)});
 return <section className="factory-review"><button className="button secondary" aria-expanded={open} onClick={()=>setOpen(!open)}>{l('مرور اندازه‌های واقعی فابریکه')}</button>{open&&<Panel title="مرور اندازه‌های واقعی فابریکه"><form className="factory-period" onSubmit={e=>{e.preventDefault();if(JSON.stringify(period)===JSON.stringify({from,to}))q.refetch();else setPeriod({from,to});}}><label>{l('از تاریخ')}<CalendarInput ariaLabel={l('از تاریخ')} value={from} max={to} onChange={setFrom} required/></label><label>{l('تا تاریخ')}<CalendarInput ariaLabel={l('تا تاریخ')} value={to} min={from} onChange={setTo} required/></label><button className="button secondary" disabled={q.isFetching} type="submit">{l('بررسی دوباره')}</button></form>
 <p className="form-info">{l('این مرور از ثبت واقعی همین دوره است؛ خروجی اولیه با موجودی قابل فروش فرق دارد. مصرف مواد و بهای تولید فقط با صلاحیت مربوط دیده می‌شود.')}</p>
 {q.isLoading?<Spinner/>:q.isError?<ErrorNotice error={q.error} retry={()=>q.refetch()}/>:d&&<>
  <div className="summary-strip"><div><span>{l('بچ‌های مرحله‌ای آغازشده')}</span><strong>{number(d.batch_starts)}</strong></div><div><span>{l('ثبت‌های خروجی اندازه‌شده')}</span><strong>{number(d.output_events)}</strong></div></div>
  <h3>{l('خروجی اولیه به تفکیک محصول و اندازه')}</h3><DataTable tableKey="factory:outputs" data={d.outputs} columns={stockColumns}/>
  <details className="factory-review-detail"><summary>{l('ضایعات و سربلوک / کف بلوک اندازه‌شده')}</summary><p>{l('درصد ضایعات فقط از ارتفاع‌های هم‌اندازه همین اصلاح بلوک محاسبه می‌شود؛ کیلوگرام مواد به سانتی‌متر تبدیل نمی‌شود.')}</p><DataTable data={d.trims} columns={[{key:'product_name',label:'محصول'},{key:'warehouse_name',label:'انبار'},{key:'profile',label:'اندازه / مشخصه'},{key:'original_mm',label:'ارتفاع اولیه (mm)',render:r=>number(r.original_mm,3)},{key:'main_mm',label:'ارتفاع محصول اصلی (mm)',render:r=>number(r.main_mm,3)},{key:'top_mm',label:'سربلوک (mm)',render:r=>number(r.top_mm,3)},{key:'bottom_mm',label:'کف بلوک (mm)',render:r=>number(r.bottom_mm,3)},{key:'loss_mm',label:'ضایعات (mm)',render:r=>number(r.loss_mm,3)},{key:'loss_percent',label:'ضایعات اندازه‌شده (%)',render:r=>number(r.loss_percent,4)}]}/></details>
  {d.inputs&&<details className="factory-review-detail"><summary>{l('مصرف خالص واقعی مواد در دوره')}</summary><p>{l('مصرف ثبت‌شده منهای برگشت مواد مصرف‌شده به انبار؛ صدور مواد به کف تولید به تنهایی مصرف نیست.')}</p><DataTable data={d.inputs} columns={stockColumns.filter(c=>c.key!=='blocks')}/></details>}
  <details className="factory-review-detail"><summary>{l('زمان ثبت‌شده کار و توقف تجهیزات')}</summary><p>{l('دقایق کارت کار، معاش یا درصد استفاده واقعی ماشین نیست. توقف فقط از تکمیل ترمیمات ثبت‌شده می‌آید.')}</p><div className="factory-time-grid"><Panel title="زمان کارت‌های کار"><DataTable data={d.job_time} columns={[{key:'name',label:'مرکز کار'},{key:'minutes',label:'دقیقه',sortType:'decimal',render:r=>number(r.minutes)}]}/></Panel><Panel title="توقف ثبت‌شده ترمیمات">{d.downtime===null?<p>{l('برای دیدن توقف تجهیزات، صلاحیت ترمیمات لازم است.')}</p>:<DataTable data={d.downtime} columns={[{key:'name',label:'مرکز کار'},{key:'minutes',label:'دقیقه',sortType:'decimal',render:r=>number(r.minutes)}]}/>}</Panel></div></details>
  {d.costs&&<details className="factory-review-detail"><summary>{l('مصارف جذب‌شده و زیان غیرعادی')}</summary><p>{l('این ارقام ثبت هزینه تازه نیست. مزد و سربار جذب‌شده قبلاً از اسناد مجاز به تولید انتقال یافته است.')}</p><div className="summary-strip"><div><span>{l('مزد جذب‌شده در تولید')}</span><strong>{money(d.costs.capitalized_labor)}</strong></div><div><span>{l('سربار جذب‌شده در تولید')}</span><strong>{money(d.costs.capitalized_overhead)}</strong></div><div><span>{l('زیان غیرعادی ثبت‌شده')}</span><strong>{money(d.costs.abnormal_loss)}</strong></div></div></details>}
 </>}
 </Panel>}</section>;
}
