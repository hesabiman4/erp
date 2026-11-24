import {useEffect,useState} from 'react';
import type {ReactNode} from 'react';
import {useNavigate,useLocation} from 'react-router-dom';
import {useQueryClient} from '@tanstack/react-query';
import {ArrowLeft,BookOpen,CheckCircle2,ChevronDown} from 'lucide-react';
import {api,money} from './api';
import type {Row} from './api';
import {useScope,useResource} from './App';
import {Panel,Spinner,ErrorNotice,DataTable} from './ui';
import {operationLabels} from './workflows';
import {formatCalendarDate} from './calendar';
import i18n from './i18n';
import {l} from './localize';
import './daily-workspace.css';

i18n.addResourceBundle('en','translation',{'میز کار من':'My daily workspace','کارهای مجاز، اسناد واقعی و قدم بعدی روشن.':'Authorized tasks, original records and a clear next step.','نوع میز کار':'Task profile','این انتخاب فقط نمایش کارها را تنظیم می‌کند؛ صلاحیت تازه نمی‌دهد.':'This selects a task view and does not grant new permissions.','فروش سریع':'Counter sales','مرکز یادگیری':'Learning centre','راهنمای همین کار':'Help with this task','مطالعه و تمرین شخصی است؛ تأیید مالی یا تصدیق مسلکی نیست.':'Personal learning and practice; not financial approval or professional certification.','نمایش موارد بیشتر':'Show more','اسناد نمایش‌شده، مجموع تمام شرکت نیست.':'Shown records are a page, not a company total.','بررسی سند':'Review document','قدم‌های خوانده‌شده':'Steps read','بازکردن بخش مربوط':'Open related workspace','تکمیل درس ثبت شد؛ ثبت مالی انجام نشد.':'Learning progress saved; no financial transaction posted.','رهنمای عملی دری':'Practical Dari guidance','نمونه‌های آموزشی است؛ معلومات واقعی تجارت نیست.':'Teaching examples, not actual business data.','راهنمای این بخش':'Guidance for this workspace'},true,true);
const language=()=>i18n.language;
i18n.addResourceBundle('ps','translation',{
 'میز کار من':'زما ورځنی کاري ځای','کارهای مجاز، اسناد واقعی و قدم بعدی روشن.':'مجاز کارونه، اصلي اسناد او روښانه بل ګام.','نوع میز کار':'د کاري ځای ډول','این انتخاب فقط نمایش کارها را تنظیم می‌کند؛ صلاحیت تازه نمی‌دهد.':'دا ټاکنه یوازې د کارونو ښودل بدلوي؛ نوی صلاحیت نه درکوي.','فروش سریع':'چټک پلور','مرکز یادگیری':'د زده کړې مرکز','راهنمای همین کار':'د همدې کار لارښوونې','مطالعه و تمرین شخصی است؛ تأیید مالی یا تصدیق مسلکی نیست.':'دا شخصي زده کړه او تمرین دی؛ مالي تایید یا مسلکي تصدیق نه دی.','نمایش موارد بیشتر':'نور ریکارډونه ښودل','اسناد نمایش‌شده، مجموع تمام شرکت نیست.':'ښودل شوي اسناد د یوې پاڼې ریکارډونه دي، د ټول شرکت مجموعه نه ده.','بررسی سند':'د سند کتنه','قدم‌های خوانده‌شده':'لوستل شوي ګامونه','بازکردن بخش مربوط':'اړونده برخه پرانیستل','تکمیل درس ثبت شد؛ ثبت مالی انجام نشد.':'د درس بشپړېدل ثبت شول؛ مالي ثبت ونه شو.','رهنمای عملی دری':'عملي لارښوونې','نمونه‌های آموزشی است؛ معلومات واقعی تجارت نیست.':'دا د زده کړې بېلګې دي؛ د سوداګرۍ حقیقي معلومات نه دي.','راهنمای این بخش':'د دې برخې لارښوونې','بازگشت':'بېرته','مبلغ کل':'ټول مبلغ','مانده':'پاتې','شماره':'شمېره','مانده ثبت‌شده':'ثبت شوې پاتې اندازه','مسوده بررسی‌شده از اصل سند':'له اصلي سند سره کتل شوې مسوده','معلومات با مدرک اصلی تأیید شده است. ثبت نهایی فقط با صلاحیت عادی انجام می‌شود؛ این مسوده هنوز اثر مالی ندارد.':'معلومات له اصلي سند سره تایید شوي دي. وروستی ثبت عادي صلاحیت غواړي؛ دا مسوده لا مالي اغېز نه لري.'
},true,true);
i18n.addResourceBundle('en','translation',{'رهنمای عملی دری':'Practical guidance'},true,true);
i18n.addResourceBundle('en','translation',{'بازگشت':'Back','مبلغ کل':'Total amount','مانده':'Balance','شماره':'Number','مانده ثبت‌شده':'Recorded balance','مسوده بررسی‌شده از اصل سند':'Draft reviewed against original evidence','معلومات با مدرک اصلی تأیید شده است. ثبت نهایی فقط با صلاحیت عادی انجام می‌شود؛ این مسوده هنوز اثر مالی ندارد.':'Fields were reviewed against the source. Ordinary posting permission is required; this draft has no financial effect.'},true,true);
function label(item:Row){return language()==='en'?item.en:language()==='ps'&&item.ps?item.ps:item.title;}
function lessonText(guide:Row,step:string[]){const translated=language()==='ps'?guide.steps_ps?.[step[0]]:null;return language()==='en'?[step[3],step[4]]:translated?[translated.title,translated.body]:[step[1],step[2]];}

function WorkQueue({initial}:{initial:Row}){
 const{businessId,locationId,showDocument}=useScope();const[data,setData]=useState<Row>(initial);const[busy,setBusy]=useState(false);const[error,setError]=useState<any>();
 useEffect(()=>{setData(initial);setError(undefined);},[initial,businessId,locationId]);
 const more=async()=>{setBusy(true);try{const next=await api.get(`/api/workspace/?queue=${initial.key}&before=${data.next_cursor}`);setData({...next,results:[...data.results,...next.results]});}catch(e){setError(e);}finally{setBusy(false);}};
 return <Panel title={label(data)} subtitle="اسناد نمایش‌شده، مجموع تمام شرکت نیست.">{error&&<ErrorNotice error={error}/>}<DataTable data={data.results||[]} columns={[{key:'number',label:'شماره سند'},{key:'date',label:'تاریخ',render:r=>formatCalendarDate(r.date)},{key:'party_name',label:'طرف حساب'},{key:'balance',label:'باقی‌مانده',render:r=>r.balance===null?'—':money(r.balance)},{key:'open',label:'',render:r=><button className="text-link" onClick={async()=>{try{showDocument(await api.get(`/api/documents/${r.id}/`));}catch(e){setError(e);}}}>{l('بررسی سند')}<ArrowLeft size={14}/></button>}]}/>{data.next_cursor&&<div className="workspace-more"><button disabled={busy} className="button secondary small" onClick={more}>{l('نمایش موارد بیشتر')}</button></div>}</Panel>;
}

export function DailyWorkspace({overview}:{overview?:ReactNode}){
 const{perform,businessId,locationId}=useScope();const navigate=useNavigate();const qc=useQueryClient();const q=useResource('/api/workspace/');const[error,setError]=useState<any>();
 useEffect(()=>setError(undefined),[businessId,locationId]);
 if(q.isLoading)return <Spinner/>;if(q.isError)return <ErrorNotice error={q.error} retry={()=>q.refetch()}/>;
 const data=q.data||{};
 return <><section className="daily-workspace"><div className="daily-heading"><div><span className="eyebrow">{l('میز کار من')}</span><h2>{l('کارهای مجاز، اسناد واقعی و قدم بعدی روشن.')}</h2></div><label>{l('نوع میز کار')}<select aria-label={l('نوع میز کار')} value={data.persona||''} onChange={async e=>{try{await api.patch('/api/workspace/',{persona:e.target.value});await qc.invalidateQueries({queryKey:['/api/workspace/']});}catch(e){setError(e);}}}>{(data.personas||[]).map((p:Row)=><option key={p.id} value={p.id}>{label(p)}</option>)}</select></label></div><p className="ledger-note">{l('این انتخاب فقط نمایش کارها را تنظیم می‌کند؛ صلاحیت تازه نمی‌دهد.')}</p>{error&&<ErrorNotice error={error}/>}<div className="daily-actions">{(data.actions||[]).map((action:string)=><button key={action} className="button secondary" onClick={()=>action==='cash_shift_open'?navigate('/operations?view=cashier'):perform(action)}>{l(operationLabels[action]||action)}<ArrowLeft size={16}/></button>)}{(data.actions||[]).includes('sale')&&<button className="button primary" onClick={()=>navigate('/sales/counter')}>{l('فروش سریع')}</button>}<button className="text-link" onClick={()=>navigate('/help')}><BookOpen size={17}/>{l('مرکز یادگیری')}</button></div><div className="work-queues">{(data.queues||[]).map((item:Row)=><WorkQueue key={`${businessId}:${locationId}:${data.persona}:${item.key}`} initial={item}/>)}</div></section>{data.persona==='owner'&&overview}</>;
}

export function LearningCentre(){
 const q=useResource('/api/guidance/');const navigate=useNavigate();const{search}=useLocation();const[topic,setTopic]=useState(new URLSearchParams(search).get('topic')||'');const[error,setError]=useState<any>();const qc=useQueryClient();const{businessId,locationId}=useScope();const[saving,setSaving]=useState(false);
 useEffect(()=>{setTopic(new URLSearchParams(search).get('topic')||'');setError(undefined);},[search,businessId]);
 if(q.isLoading)return <Spinner/>;if(q.isError)return <ErrorNotice error={q.error} retry={()=>q.refetch()}/>;
 const topics:Row[]=q.data?.topics||[];const selected=topics.find(g=>g.id===topic)||topics[0];
 return <div className="learning-centre"><div className="daily-heading"><div><span className="eyebrow">{l('رهنمای عملی دری')}</span><h1>{l('مرکز یادگیری')}</h1><p>{l('مطالعه و تمرین شخصی است؛ تأیید مالی یا تصدیق مسلکی نیست.')}</p></div><BookOpen size={30}/></div>{error&&<ErrorNotice error={error}/>}<div className="learning-layout"><nav aria-label={l('مرکز یادگیری')}>{topics.map(g=><button className={g.id===selected?.id?'active':''} key={g.id} onClick={()=>setTopic(g.id)}>{label(g)}<small>{g.completed.length}/{g.steps.length}</small></button>)}</nav>{selected?<Panel title={label(selected)} subtitle="نمونه‌های آموزشی است؛ معلومات واقعی تجارت نیست.">{selected.steps.map((step:string[],i:number)=><article className="learning-step" key={step[0]}><span className="lesson-number">{i+1}</span><div><h3>{lessonText(selected,step)[0]}</h3><p lang={language()} dir={language()==='en'?'ltr':'rtl'}>{lessonText(selected,step)[1]}</p><label className="check-field"><input type="checkbox" disabled={saving} checked={selected.completed.includes(step[0])} onChange={async e=>{const completed=e.target.checked?[...selected.completed,step[0]]:selected.completed.filter((v:string)=>v!==step[0]);const previous=q.data;const key=['/api/guidance/',businessId,locationId];setSaving(true);qc.setQueryData(key,{...previous,topics:topics.map(g=>g.id===selected.id?{...g,completed}:g)});try{await api.patch('/api/guidance/',{topic:selected.id,completed});await qc.invalidateQueries({queryKey:key});}catch(err){qc.setQueryData(key,previous);setError(err);}finally{setSaving(false);}}}/><CheckCircle2 size={15}/>{l('قدم‌های خوانده‌شده')}</label></div></article>)}<div className="workspace-more"><button className="button primary" onClick={()=>navigate(selected.path)}>{l('بازکردن بخش مربوط')}<ArrowLeft size={16}/></button></div></Panel>:<p>{l('دسترسی محدود')}</p>}</div></div>;
}

export function ContextualGuidance(){
 const location=useLocation();const q=useResource('/api/guidance/');
 const key=location.pathname.startsWith('/sales')?'sales':location.pathname.startsWith('/purchases')?'purchasing':location.pathname.startsWith('/production')?'production':location.pathname.startsWith('/accounting')?'accounting':location.pathname.startsWith('/employees')?'payroll':location.pathname.startsWith('/money')?'cash':['/inventory','/transfers'].includes(location.pathname)?'warehouse':null;
 const guide=q.data?.topics?.find((g:Row)=>g.id===key);const navigate=useNavigate();
 if(!guide)return null;
 return <details className="contextual-guidance"><summary><BookOpen size={16}/>{l('راهنمای همین کار')}<ChevronDown size={15}/></summary><p lang={language()} dir={language()==='en'?'ltr':'rtl'}>{lessonText(guide,guide.steps[0])[1]}</p><button className="text-link" onClick={()=>navigate(`/help?topic=${guide.id}`)}>{l('مرکز یادگیری')}<ArrowLeft size={15}/></button></details>;
}
