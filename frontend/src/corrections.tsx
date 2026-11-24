import './correction-copy';
import './corrections.css';
import {useState} from 'react';
import {useQueryClient} from '@tanstack/react-query';
import {useNavigate,useParams,useLocation} from 'react-router-dom';
import {useScope,useResource} from './App';
import {OperationForm} from './workflows';
import {Field,SimpleForm,Panel,SectionHead,ErrorNotice,Spinner} from './ui';
import {money,number,today,normalizeDigits} from './api';
import type {Row} from './api';
import {formatCalendarDate} from './calendar';
import {l} from './localize';
import Decimal from 'decimal.js';

export function CorrectionLink({document:d}:{document:Row}){
 const navigate=useNavigate();const{businessId}=useScope();
 return d.state==='posted'?<button className="button secondary small" onClick={()=>navigate(`/documents/${d.id}/correct?business=${businessId}`)}>{l('اصلاح با حفظ سند اصلی')}</button>:null;
}
export function CorrectionWorkspace(){
 const{documentId}=useParams();const{businessId}=useScope();const expected=new URLSearchParams(useLocation().search).get('business');
 if(expected&&expected!==businessId)return <ErrorNotice error={l('تجارت مربوط به سند را از سرصفحه انتخاب کنید. دسترسی سرور همیشه بررسی می‌شود.')}/>;
 return <CorrectionPage key={`${businessId}:${documentId}`} id={documentId||''}/>;
}
function CorrectionPage({id}:{id:string}){
 const navigate=useNavigate();const{businessId,showDocument}=useScope();const qc=useQueryClient();const[choice,setChoice]=useState('');const q=useResource(`/api/documents/${id}/correction/`,/^\d+$/.test(id));
 if(!/^\d+$/.test(id))return <ErrorNotice error={l('سند پیدا نشد')}/>;
 if(q.isLoading)return <Spinner/>;if(q.isError)return <ErrorNotice error={q.error} retry={()=>q.refetch()}/>;if(!q.data)return null;
 const d=q.data.document;const option=(q.data.options||[]).find((o:Row)=>o.action===choice);
 return <div className="correction-workspace"><SectionHead title="اصلاح با حفظ سند اصلی" description="سند اصلی را بررسی کنید، نوع اصلاح را انتخاب و اثر آن را پیش از ثبت بخوانید." actions={<button className="button secondary" onClick={()=>navigate(`/documents/${id}?business=${businessId}`)}>{l('بازگشت به سند اصلی')}</button>}/>
  <Panel title={d.number}><div className="document-summary"><div><span>{l('تاریخ سند')}</span><strong>{formatCalendarDate(d.date)}</strong></div><div><span>{l('طرف حساب')}</span><strong>{d.party_name||d.data.customer_name||'—'}</strong></div><div><span>{l('مبلغ کل')}</span><strong>{money(d.amount)}</strong></div><div><span>{l('مانده')}</span><strong>{money(d.balance)}</strong></div></div><p className="form-info">{l('دیدن این رهنما حساب یا موجودی را تغییر نمی‌دهد. تاریخ، صلاحیت، پول و موجودی هنگام ثبت دوباره بررسی می‌شود.')}</p></Panel>
  <Panel title="چه چیزی باید اصلاح شود؟"><div className="correction-choices">{q.data.options.map((o:Row)=><button className={'correction-choice '+(choice===o.action?'selected':'')} key={o.action} aria-pressed={choice===o.action} onClick={()=>setChoice(o.action)}><strong>{l(o.title)}</strong><span>{l(o.effect)}</span></button>)}</div>{!q.data.options.length&&<p>{l('برای این سند و صلاحیت شما، اصلاح خودکار عمومی وجود ندارد. اصل سند را برای بررسی به حسابدار مجاز نشان دهید.')}</p>}</Panel>
  {option&&<Panel title={option.title}><p className="form-info">{l(option.effect)}</p><OperationForm key={choice} action={choice} initial={{...option.initial,source_document:d}} onSuccess={posted=>{qc.invalidateQueries();if(posted)showDocument(posted);}}/></Panel>}
  {q.data.related.length>0&&<Panel title="اسناد مرتبط"><div className="action-row">{q.data.related.map((r:Row)=><button className="button secondary small" key={r.id} onClick={()=>showDocument(r)}><bdi>{r.number}</bdi></button>)}</div></Panel>}
 </div>;
}

export function LinkedReturnForm({action,documents,initial,submit}:{action:string,documents:Row[],initial:Row,submit:(payload:Row,action?:string)=>Promise<void>}){
 const sale=action==='sale_return';const[source,setSource]=useState(String(initial[sale?'invoice':'receipt']||''));const[bill,setBill]=useState(String(initial.bill||''));const{catalog}=useScope();
 const q=useResource(`/api/documents/${source}/correction/${bill?'?bill='+encodeURIComponent(bill):''}`,!!source);
 const details=q.data?.returns;const options=documents.filter(d=>d.kind===(sale?'sale':'purchase_receive')&&d.state==='posted');
 return <><div className="form-grid"><Field field={{key:sale?'invoice':'receipt',label:sale?'بل فروش اصلی':'رسید خرید اصلی',type:'select',required:true,options:options.map(d=>({value:d.id,label:d.number}))}} value={source} onChange={v=>{setSource(v);setBill('');}}/>
 {!sale&&details&&<Field field={{key:'bill',label:'بل تأمین‌کننده مربوط',type:'select',options:[{value:'unbilled',label:'بخش بل‌نشده خرید'},...details.bills.map((b:Row)=>({value:b.id,label:b.number}))],required:true}} value={bill||'unbilled'} onChange={v=>setBill(v==='unbilled'?'':v)}/>}</div>
 {q.isLoading&&source&&<Spinner/>}{q.isError&&<ErrorNotice error={q.error}/>}
 {details&&!q.isError&&<ReturnLinesForm key={source+':'+bill} sale={sale} source={source} bill={bill} details={details} products={catalog.products||[]} submit={submit}/>}
 </>;
}
function ReturnLinesForm({sale,source,bill,details,products,submit}:{sale:boolean,source:string,bill:string,details:Row,products:Row[],submit:(payload:Row,action?:string)=>Promise<void>}){
 const[quantities,setQuantities]=useState<Record<string,string>>({});const[blocks,setBlocks]=useState<Record<string,string>>({});const stock=useResource('/api/stock/',!sale&&details.lines.some((r:Row)=>r.unit==='cm'));
 return <>{stock.isError&&<ErrorNotice error={stock.error}/>}<SimpleForm fields={[{key:'date',label:'تاریخ سند',type:'date',default:today(),required:true},{key:'reason',label:'دلیل برگشت',type:'textarea',required:true,span:true}]} onSubmit={async values=>{
  const lines=[];for(const row of details.lines){const text=normalizeDigits(quantities[row.index]||'0');let qty:Decimal;try{qty=new Decimal(text);}catch{throw Error(l('مقدار معتبر برای برگشت وارد کنید.'));}if(!qty.isFinite()||qty.isNegative())throw Error(l('مقدار معتبر برای برگشت وارد کنید.'));if(qty.isZero())continue;const limit=new Decimal(String(sale&&row.unit==='cm'?row.remaining_sheets:row.remaining_quantity));if(qty.gt(limit))throw Error(l('مقدار برگشت از مانده مجاز بیشتر است.'));lines.push({index:row.index,...(sale&&row.unit==='cm'?{sheet_count:text}:{quantity:text}),...(!sale&&row.unit==='cm'?{block:blocks[row.index]}:{})});}
  if(!lines.length)throw Error(l('حداقل یک قلم را برای برگشت انتخاب کنید.'));
  await submit({...values,[sale?'invoice':'receipt']:source,...(bill?{bill}:{}),lines},sale?'sales_return':'purchase_return');
 }}>
 <p className="form-info">{l('فقط مقدار واقعی برگشتی را وارد کنید؛ صفر یعنی این قلم برگشت نمی‌شود. اعتبار نهایی و بهای موجودی هنگام ثبت محاسبه می‌شود.')}</p>
 <div className="return-lines">{details.lines.map((row:Row)=><section key={row.index} className="return-line"><header><strong>{row.product_name||products.find(p=>p.id===row.product)?.name}</strong><span>{l('مانده قابل برگشت')}: <bdi>{number(row.remaining_quantity,6)} {row.unit}</bdi>{sale&&row.unit==='cm'&&<> · <bdi>{number(row.thickness_mm)} mm</bdi></>}</span></header>
 {sale||row.unit!=='cm'?<Field field={{key:`return-quantity-${row.index}`,label:sale&&row.unit==='cm'?'تعداد ورق برگشتی اسفنج':'مقدار برگشت',type:'number'}} value={quantities[row.index]||''} onChange={v=>setQuantities({...quantities,[row.index]:v})}/>:<Field field={{key:`return-block-${row.index}`,label:'قطعه کامل برگشتی به تأمین‌کننده',type:'select',options:(stock.data?.blocks||[]).filter((b:Row)=>b.product===row.product&&b.warehouse===details.warehouse&&['ready','reserved'].includes(b.status)&&new Decimal(String(b.reserved_height_mm)).isZero()&&new Decimal(String(b.remaining_height_mm)).gt(0)).map((b:Row)=>({value:b.id,label:`${b.code} · ${number(new Decimal(String(b.remaining_height_mm)).div(10).toString(),3)} cm`}))}} value={blocks[row.index]||''} onChange={v=>{setBlocks({...blocks,[row.index]:v});const block=stock.data?.blocks?.find((b:Row)=>String(b.id)===String(v));setQuantities({...quantities,[row.index]:block?new Decimal(String(block.remaining_height_mm)).div(10).toString():''});}}/>}
 </section>)}</div>
 </SimpleForm></>;
}
