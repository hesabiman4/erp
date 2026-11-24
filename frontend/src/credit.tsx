import './credit-copy';
import {useState} from 'react';
import {useQueryClient} from '@tanstack/react-query';
import {api,money,number} from './api';
import {useResource,useScope,hasPermission} from './App';
import {ErrorNotice,Panel,Spinner} from './ui';
import {l} from './localize';
export function CustomerCreditCard({party}:{party:number}){
 const{business}=useScope();const allowed=hasPermission(business,'settings.manage','sales.credit_manage','sales.credit_summary');const q=useResource('/api/credit/?party='+party,allowed);
 if(!allowed)return null;return <section className="customer-credit-card" aria-label={l('اعتبار جاری مشتری')}>{q.isLoading?<Spinner/>:q.isError?<ErrorNotice error={q.error}/>:<><h3>{l('اعتبار جاری مشتری')}</h3><div className="credit-summary-grid">{[['سقف نسیه',q.data?.limit],['مانده بل‌ها',q.data?.debt],['تعهد سفارش‌ها',q.data?.order_commitments],['اعتبار قابل استفاده',q.data?.available]].map(([label,value])=><div key={label}><span>{l(label)}</span><strong>{value===null?l('بدون سقف عددی'):money(value)}</strong></div>)}</div><p>{l('این خلاصه اعتبار جاری همه موقعیت‌های همین تجارت است؛ با فیلتر تاریخی صورت‌حساب فرق دارد.')}</p>{q.data?.credit_hold&&<p className="text-red">{l('فروش نسیه این مشتری متوقف است.')}</p>}{q.data?.block_overdue&&<p>{l('نسیه تازه با بل سررسیدگذشته، استثنای مجاز می‌خواهد.')}</p>}<small>{l('مهلت پرداخت')}: {number(q.data?.payment_terms_days)} {l('روز')}</small></>}</section>;
}
export function CreditPolicyPanel(){
 const{business,catalog,notify}=useScope();const enabled=hasPermission(business,'settings.manage');const[v,setV]=useState<boolean|null>(null);const[busy,setBusy]=useState(false);const[error,setError]=useState<unknown>();const qc=useQueryClient();if(!enabled)return null;
 const original=catalog.business?.settings?.credit_management?.reserve_orders===true;
 return <Panel title="سیاست نسیه و تعهد سفارش" subtitle="بل‌های فروش و طلب آغازین در اعتبار حساب می‌شود. پیش‌پرداخت فقط پس از تخصیص، مانده بل را کم می‌کند."><form className="settings-form" onSubmit={async e=>{e.preventDefault();setBusy(true);try{await api.patch('/api/credit/',{reserve_orders:v??original});await qc.invalidateQueries();notify('سیاست نسیه ذخیره شد.');setV(null);}catch(e){setError(e);}finally{setBusy(false);}}}><label className="check-field"><input type="checkbox" checked={v??original} onChange={e=>setV(e.target.checked)}/>{l('سفارش‌های فروش اجرا‌نشده اعتبار مشتری را رزرو کند')}</label><p className="settings-hint">{l('رزرو اعتبار، ثبت طلب یا فروش نیست. هنگام بل‌کردن سفارش، همان تعهد دوباره شمرده نمی‌شود. تعهد سفارش به نرخ خالص سفارش محاسبه می‌شود.')}</p><p className="settings-hint">{l('سقف خالی: بدون سقف عددی. صفر: نسیه مجاز نیست. توقف نسیه و کنترول سررسید برای هر مشتری جدا تنظیم می‌شود.')}</p>{!!error&&<ErrorNotice error={error}/>}<button className="button primary" type="submit" disabled={busy}>{l('ذخیره سیاست نسیه')}</button></form></Panel>;
}
