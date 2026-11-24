import './setup-localization-copy';
import {useState} from 'react';
import {BookOpen,Search} from 'lucide-react';
import {useScope} from './App';
import {money,number} from './api';
import type {Row} from './api';
import {DataTable} from './ui';
import {groupNames} from './statements';
import {l} from './localize';
import {useTranslation} from 'react-i18next';
export function AccountBrowser({data}:{data:Row}){
 const{businessId}=useScope();const{i18n}=useTranslation();const manualLanguage=i18n.language.startsWith('en')?'en':i18n.language.startsWith('ps')?'ps-AF':'fa-AF';const[search,setSearch]=useState('');const[category,setCategory]=useState('');const[selected,setSelected]=useState<Row|null>(null);
 const types:Record<string,string>={asset:'دارایی',liability:'بدهی',equity:'حقوق مالک',income:'درآمد',expense:'مصرف'};
 const rows:Row[]=(data.rows||[]).filter((r:Row)=>(!category||r.category===category)&&`${r.number} ${r.code} ${r.name} ${l(r.name)}`.toLowerCase().includes(search.toLowerCase()));
 const credit=selected&&selected.code!=='DRAWINGS'&&(selected.category==='liability'||selected.category==='equity'||selected.category==='income'||['ACCUM_DEPR','INVENTORY_ALLOWANCE'].includes(selected.code));
 return <div className="account-browser"><div className="account-guide-strip"><div><strong>{l('هر عملیات، حساب‌های مربوط را خودکار ثبت می‌کند.')}</strong><p>{l('برای شروع، دارایی، بدهی، درآمد و مصرف را بشناسید؛ به حساب‌های کنترلی سند دستی نزنید.')}</p></div><a className="button secondary small" href={`/api/accounting-guide/?business=${businessId}&language=${manualLanguage}`}><BookOpen size={17}/>{l('دریافت راهنمای کامل حساب‌ها')} · PDF</a><small>{l('راهنما به دری، پشتو و انگلیسی موجود است.')}</small></div><div className="chart-controls"><div className="search-input"><Search size={16}/><input aria-label={l('جستجوی حساب')} placeholder={l('شماره، نام یا کد حساب')} value={search} onChange={e=>setSearch(e.target.value)}/></div><select aria-label={l('نوع حساب')} value={category} onChange={e=>setCategory(e.target.value)}><option value="">{l('همه انواع حساب')}</option>{Object.entries(types).map(([key,label])=><option key={key} value={key}>{l(label)}</option>)}</select><small>{number(rows.length)} {l('حساب')}</small></div>
 <DataTable data={rows} onRow={setSelected} columns={[{key:'number',label:'شماره حساب'},{key:'name',label:'شرح حساب',render:r=><div><strong>{l(r.name)}</strong><br/><small><bdi>{r.code}</bdi></small></div>},{key:'category',label:'نوع حساب',render:r=>l(types[r.category]||r.category)},{key:'group',label:'گروه گزارش',render:r=>l(groupNames[r.group]||r.group)},{key:'balance',label:'بدهکار منهای بستانکار',render:r=><bdi>{money(r.balance)}</bdi>},{key:'control',label:'روش ثبت',render:r=><span className={`badge ${r.control?'amber':''}`}>{l(r.control?'از عملیات مربوط':'ثبت با مجوز حسابدار')}</span>}]}/>
 {selected&&<section className="account-insight"><h3>{l(selected.name)} · <bdi>{selected.number}</bdi></h3><p>{l('ماهیت معمول حساب')}: <strong>{l(credit?'بستانکار':'بدهکار')}</strong> · {l('گروه گزارش')}: {l(groupNames[selected.group]||selected.group)}</p><p>{l(selected.control?'این حساب به دفتر جزئیات مانند انبار، مشتری، کارمند یا بانک وصل است. ثبت را از فروش، خرید، معاش یا عملیات مربوط انجام دهید؛ سند دستی مجاز نیست.':'این حساب برای طبقه‌بندی درآمد، مصرف یا مانده‌های دیگر استفاده می‌شود. نوع عملیات و مجوز حسابدار مشخص می‌کند کدام ثبت مجاز است.')}</p><p>{l('منفی بودن ستون بدهکار منهای بستانکار برای حساب بستانکار معمول است؛ به معنی زیان یا اشتباه قطعی نیست.')}</p></section>}</div>;
}

