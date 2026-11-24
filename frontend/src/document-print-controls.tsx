import './print-profile-copy';
import {useState} from 'react';
import {Printer} from 'lucide-react';
import {useScope,useResource} from './App';
import type {Row} from './api';
import {number} from './api';
import {ErrorNotice,Spinner,DataTable} from './ui';
import {l} from './localize';
import {printLanguages} from './print-profile-extensions';
import {formatCalendarDate} from './calendar';

export function DocumentPrintControls({document:d}:{document:Row}){
 const{catalog,businessId}=useScope();const[language,setLanguage]=useState('');const[printer,setPrinter]=useState('');const[history,setHistory]=useState(false);const profile=catalog.business?.settings?.print_profile||{};
 const q=useResource(`/api/documents/${d.id}/print-history/`,history);
 const print=(compact=false)=>{const p=new URLSearchParams({business:businessId,copy:'1'});if(language)p.set('language',language);if(printer)p.set('printer',printer);if(compact)p.set('compact','1');window.open(`/api/documents/${d.id}/print/?${p}`,'_blank');};
 return <div className="document-print-controls"><div className="document-print-options"><label>{l('زبان سند')}<select aria-label={l('زبان سند')} value={language} onChange={e=>setLanguage(e.target.value)}><option value="">{l('پیروی از تنظیم عمومی')}</option>{printLanguages.map(o=><option key={o.value} value={o.value}>{l(o.label)}</option>)}</select></label><label>{l('پروفایل چاپ')}<select aria-label={l('پروفایل چاپ')} value={printer} onChange={e=>setPrinter(e.target.value)}><option value="">{l('پیروی از تنظیم عمومی')}</option>{(profile.printer_profiles||[]).map((p:Row)=><option key={p.id} value={p.id}>{p.name} · {p.paper}</option>)}</select></label><button className="button secondary" onClick={()=>print()}><Printer size={17}/>{l('چاپ سند / ذخیره PDF')}</button><button className="button secondary" onClick={()=>print(true)}>{l('رسید کوچک')}</button><button className="text-link" onClick={()=>setHistory(!history)} aria-expanded={history}>{l('سابقه ساخت نمای چاپ')}</button></div>
 {history&&<section className="print-history"><p className="form-info">{l('این سابقه ساخت نمای چاپ را ثبت می‌کند. چاپ فزیکی یا ذخیره موفق PDF از مرورگر تأیید نشده است.')}</p><button className="button secondary small" onClick={()=>q.refetch()}>{l('تازه‌سازی')}</button>{q.isLoading?<Spinner/>:q.isError?<ErrorNotice error={q.error}/>:q.data&&<><p>{l('تعداد نماهای ساخته‌شده')}: {number(q.data.count)} · {l('حداکثر پنجاه مورد آخر نمایش داده می‌شود.')}</p><DataTable tools={false} data={q.data.results} columns={[{key:'generated_at',label:'زمان ساخت',render:r=>formatCalendarDate(new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kabul'}).format(new Date(r.generated_at)))+' '+new Date(r.generated_at).toLocaleTimeString('en-GB',{timeZone:'Asia/Kabul'})},{key:'actor',label:'کاربر'},{key:'language',label:'زبان سند',render:r=>l(printLanguages.find(o=>o.value===r.language)?.label||'برای سابقه قدیمی ثبت نشده')},{key:'paper',label:'کاغذ چاپگر'},{key:'content_sha256',label:'اثر انگشت نمای ساخته‌شده',render:r=><code className="print-content-hash">{r.content_sha256||l('برای سابقه قدیمی ثبت نشده')}</code>}]} /></>}</section>}
 </div>;
}
