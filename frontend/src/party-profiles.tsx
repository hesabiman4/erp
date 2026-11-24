import './party-copy';
import './party-profiles.css';
import {useEffect,useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import Decimal from 'decimal.js';
import {Plus,Trash2} from 'lucide-react';
import {useScope,useResource,hasPermission} from './App';
import {Field,ErrorNotice} from './ui';
import type {FieldDef} from './ui';
import {api,money,number} from './api';
import type {Row} from './api';
import {l} from './localize';

export function PartyEditor({initial={},kind,onSuccess}:{initial?:Row,kind?:string,onSuccess:()=>void}){
 const{businessId}=useScope();return <Editor key={`${businessId}:${initial.id||'new'}:${kind||''}`} initial={initial} fixedKind={kind} onSuccess={onSuccess}/>;
}
function Editor({initial,fixedKind,onSuccess}:{initial:Row,fixedKind?:string,onSuccess:()=>void}){
 const{business,businessId}=useScope();const[kind,setKind]=useState(fixedKind||initial.kind||'customer');
 const[v,setV]=useState<Row>({...initial,name:initial.name||'',phone:initial.phone||'',credit_hold:initial.credit_hold||false,block_overdue:initial.block_overdue||false});const[contacts,setContacts]=useState<Row[]>(initial.contacts||[]);const[busy,setBusy]=useState(false);const[error,setError]=useState('');const[search,setSearch]=useState({name:'',phone:''});
 useEffect(()=>{const timer=setTimeout(()=>setSearch({name:v.name||'',phone:v.phone||''}),350);return()=>clearTimeout(timer);},[v.name,v.phone]);
 const duplicate=useQuery({queryKey:['party-duplicates',businessId,kind,initial.id,search],queryFn:()=>api.post('/api/party-tools/duplicates/',{kind,...search,exclude:initial.id}),enabled:!!(search.name||search.phone)});
 const groups=useResource(`/api/party-tools/groups/?kind=${kind}`);
 const manager=hasPermission(business,'settings.manage',kind==='supplier'?'purchases.terms_manage':'sales.credit_manage');
 const basic:FieldDef[]=[{key:'name',label:'نام',required:true},{key:'phone',label:'تلفن'},{key:'address',label:'آدرس'},{key:'delivery_address',label:'آدرس تحویل کالا'},{key:'registration_number',label:'شماره ثبت / نمبر تشخیصیه مالیه'},{key:'notes',label:'یادداشت',type:'textarea',span:true}];
 const terms:FieldDef[]=manager?[{key:'payment_terms_days',label:'مهلت پرداخت (روز)',type:'number',required:true},...(kind==='customer'?[{key:'credit_limit',label:'سقف نسیه',type:'number' as const,help:'سقف خالی: بدون سقف عددی. صفر: نسیه مجاز نیست. توقف نسیه و کنترول سررسید برای هر مشتری جدا تنظیم می‌شود.'},{key:'credit_hold',label:'توقف فروش نسیه',type:'checkbox' as const},{key:'block_overdue',label:'توقف نسیه هنگام سررسید گذشته',type:'checkbox' as const}]:[])]:[];
 const field=(f:FieldDef)=><Field key={f.key} field={f} value={v[f.key]??(f.key==='payment_terms_days'?0:'')} onChange={value=>setV({...v,[f.key]:value})}/>;
 return <form className="party-editor" onSubmit={async e=>{e.preventDefault();if(busy)return;setBusy(true);setError('');try{
  const payload:Row={kind,contacts};for(const f of [...basic,...terms])payload[f.key]=v[f.key]??(f.key==='payment_terms_days'?0:f.type==='checkbox'?false:'');payload.group_name=v.group_name||'';
  if('payment_terms_days' in payload)payload.payment_terms_days=Number(payload.payment_terms_days||0);if('credit_limit' in payload&&payload.credit_limit==='')payload.credit_limit=null;
  if(initial.id)await api.patch(`/api/catalog/parties/${initial.id}/`,payload);else await api.post('/api/catalog/parties/',payload);onSuccess();
 }catch(err){setError(err instanceof Error?err.message:String(err));}finally{setBusy(false);}}}>
 {!fixedKind&&!initial.id&&<Field field={{key:'kind',label:'نوع',type:'select',required:true,options:[...(hasPermission(business,'settings.manage','sales.post')?[{value:'customer',label:'مشتری'}]:[]),...(hasPermission(business,'settings.manage','purchases.post')?[{value:'supplier',label:'تأمین‌کننده'}]:[])]}} value={kind} onChange={setKind}/>}
 <div className="form-grid">{basic.map(field)}<label className="field"><span>{l('گروه تجارتی')}</span><input name="group_name" list="party-groups" value={v.group_name||''} maxLength={80} onChange={e=>setV({...v,group_name:e.target.value})}/><datalist id="party-groups">{(groups.data?.groups||[]).map((g:string)=><option key={g} value={g}/>)}</datalist></label></div>
 {duplicate.isError&&<ErrorNotice error={duplicate.error} retry={()=>duplicate.refetch()}/>}
 {duplicate.data&&duplicate.data.count>0&&<aside className="party-duplicate-warning" role="status"><strong>{l('حساب‌های احتمالاً تکراری')}: {number(duplicate.data.count)}</strong><p>{l('پیش از ساخت حساب تازه، نام و تلفن را بررسی کنید. این هشدار حساب‌ها را خودکار یکجا نمی‌کند.')}</p><ul>{duplicate.data.results.map((p:Row)=><li key={p.id}><strong>{p.name}</strong> · <bdi dir="ltr">{p.phone||'—'}</bdi></li>)}</ul></aside>}
 {terms.length>0&&<section className="party-form-section"><h3>{l(kind==='supplier'?'شرایط پرداخت تأمین‌کننده':'شرایط نسیه مشتری')}</h3><div className="form-grid">{terms.map(field)}</div></section>}
 <section className="party-form-section"><div className="line-header"><h3>{l('اشخاص تماس')}</h3><button type="button" className="button secondary small" disabled={contacts.length>=20} onClick={()=>setContacts([...contacts,{name:'',role:'',phone:'',email:''}])}><Plus size={15}/>{l('افزودن شخص تماس')}</button></div><p className="ledger-note">{l('تلفن اصلی حساب برای جستجو حفظ می‌شود؛ اشخاص خرید، پرداخت و تحویل را جدا ثبت کنید.')}</p>
 {contacts.map((c,index)=><div className="party-contact-editor" key={index}><div className="form-grid">{[{key:'name',label:'نام شخص تماس',required:true},{key:'role',label:'وظیفه / مسؤولیت'},{key:'phone',label:'تلفن شخص تماس'},{key:'email',label:'ایمیل شخص تماس'}].map(f=><Field key={f.key} field={{...f,key:`contact-${f.key}-${index}`}} value={c[f.key]||''} onChange={value=>setContacts(contacts.map((x,i)=>i===index?{...x,[f.key]:value}:x))}/>)}</div><button type="button" className="icon-button danger" aria-label={l('حذف شخص تماس')} onClick={()=>setContacts(contacts.filter((_,i)=>i!==index))}><Trash2 size={17}/></button></div>)}</section>
 {error&&<ErrorNotice error={error}/>}<footer className="form-footer"><span>{l('مشخصات تازه اسناد ثبت‌شده قبلی را تغییر نمی‌دهد.')}</span><button className="button primary" type="submit" disabled={busy}>{l('ثبت مشخصات')}</button></footer>
 </form>;
}

export function PriceBasisHint({price,catalogPrice,agreement,order}:{price:unknown,catalogPrice:unknown,agreement?:Row,order?:unknown}){
 let basis='نرخ متفاوت؛ سفارش مرتبط یا صلاحیت تغییر نرخ هنگام ثبت بررسی می‌شود.';
 try{const selected=new Decimal(String(price));if(agreement&&selected.eq(String(agreement.unit_price)))basis='این نرخ با قرارداد مؤثر مشتری مطابق است.';else if(selected.eq(String(catalogPrice)))basis='این نرخ با نرخ عمومی محصول مطابق است.';else if(order)basis='نرخ سفارش مرتبط را پیش از ثبت بررسی کنید.';}catch{return null;}
 return <div className="price-basis-hint"><strong>{l('مبنای نرخ')}</strong><span>{l(basis)}</span><small>{l('نرخ عمومی')}: {money(catalogPrice)}{agreement&&<> · {l('نرخ قراردادی مشتری')}: {money(agreement.unit_price)}</>}</small></div>;
}
export function PartyContacts({party}:{party:Row}){
 return <><dl className="party-contact-details">{[['گروه تجارتی',party.group_name],['شماره ثبت / نمبر تشخیصیه مالیه',party.registration_number],['آدرس تحویل کالا',party.delivery_address],['مهلت پرداخت (روز)',number(party.payment_terms_days||0)]].map(([label,value])=><div key={label}><dt>{l(label)}</dt><dd>{value||'—'}</dd></div>)}</dl>{party.contacts?.length>0&&<section className="party-contact-cards"><h3>{l('اشخاص تماس')}</h3>{party.contacts.map((c:Row,index:number)=><article key={index}><strong>{c.name}</strong><span>{c.role}</span><bdi dir="ltr">{c.phone}</bdi><bdi dir="ltr">{c.email}</bdi></article>)}</section>}</>;
}
