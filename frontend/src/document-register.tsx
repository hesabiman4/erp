import './register-copy';
import {useState} from 'react';
import {useLocation} from 'react-router-dom';
import {useQuery} from '@tanstack/react-query';
import {api,money,number,rows} from './api';
import type {Row} from './api';
import {useScope} from './App';
import {DataTable,ErrorNotice,Spinner} from './ui';
import type {Column} from './ui';
import type {TableQuery,TableFilter} from './data-table';
import {l} from './localize';

export function DocumentRegister(props:{kind:string,columns:Column[],search?:string}){
 const{businessId,locationId,userId}=useScope();const locationSearch=useLocation().search;
 return <RegisterState key={[userId,businessId,locationId,props.kind,props.search||'',locationSearch].join(':')} {...props}/>;
}
function RegisterState({kind,columns,search=''}:{kind:string,columns:Column[],search?:string}){
 const{businessId,locationId,userId,showDocument}=useScope();
 const payment=new URLSearchParams(useLocation().search).get('filter')||'';const initialFilters:TableQuery['filters']=['paid','unpaid'].includes(payment)?{payment}:{};
 const[query,setQuery]=useState<TableQuery>({search,sort:null,filters:initialFilters});const[offset,setOffset]=useState(0);
 const params=new URLSearchParams({kind,limit:'100',offset:String(offset),q:query.search});
 if(query.sort)params.set('sort',(query.sort.direction==='desc'?'-':'')+query.sort.key);
 for(const[id,value]of Object.entries(query.filters)){if(typeof value==='string'&&value)params.set(id,value);else if(value&&typeof value==='object'){if(value.from)params.set('from',value.from);if(value.to)params.set('to',value.to);}}
 const q=useQuery({queryKey:['document-register',businessId,locationId,params.toString()],queryFn:()=>api.get('/api/document-register/?'+params),placeholderData:previous=>previous});
 const filters:TableFilter[]=[{id:'state',label:'وضعیت سند',type:'status',options:[{value:'draft',label:'پیش‌نویس'},{value:'posted',label:'ثبت‌شده'},{value:'cancelled',label:'لغوشده'},{value:'converted',label:'تبدیل‌شده'}],value:r=>r.state},{id:'date',label:'تاریخ سند',type:'date',value:r=>r.date}];
 if(['sale','purchase_bill','opening_receivable','opening_payable','expense_post','asset_acquire'].includes(kind))filters.push({id:'payment',label:'وضعیت پرداخت',type:'status',options:[{value:'unpaid',label:'دارای مانده'},{value:'partial',label:'قسمی پرداخت‌شده'},{value:'paid',label:'تسویه‌شده'},{value:'overdue',label:'سررسید گذشته'}],value:r=>r.balance});
 const changed=(next:TableQuery)=>{if(JSON.stringify(next)!==JSON.stringify(query)){setQuery(next);setOffset(0);}};
 const data=q.data as Row|undefined;
 return <div className="document-register">
  {q.isError&&<ErrorNotice error={q.error} retry={()=>q.refetch()}/>}
  {q.isLoading&&<Spinner/>}
  <div className="summary-strip" aria-live="polite" aria-busy={q.isFetching}>
   <div><span>{l('تمام اسناد مطابق فیلتر')}</span><strong>{data?number(data.count):'—'}</strong></div>
   <div><span>{l('مبلغ تمام نتایج مجاز')}</span><strong>{data?money(data.totals.amount):'—'}</strong></div>
   {filters.some(f=>f.id==='payment')&&<div><span>{l('مانده تمام نتایج مجاز')}</span><strong>{data?money(data.totals.balance):'—'}</strong></div>}
  </div>
  {q.isFetching&&data&&<p role="status">{l('در حال تازه‌سازی نتایج؛ ارقام قبلی تا پایان بررسی نمایش داده می‌شود.')}</p>}
  <DataTable data={rows(data)} columns={columns} onRow={showDocument} filters={filters} tableKey={'documents:'+kind} preferenceScope={{userId,businessId,locationId}} remote={{onQuery:changed,busy:q.isFetching,initialSearch:search,initialFilters}}/>
  {data&&data.count>100&&<div className="pagination"><span>{number(data.count?data.offset+1:0)}–{number(data.offset+rows(data).length)} {l('از')} {number(data.count)} {l('سند')}</span><div><button className="button secondary small" disabled={q.isFetching||offset===0} onClick={()=>setOffset(Math.max(offset-100,0))}>{l('صفحه قبل')}</button><button className="button secondary small" disabled={q.isFetching||data.next_offset===null} onClick={()=>setOffset(data.next_offset)}>{l('صفحه بعد')}</button></div></div>}
 </div>;
}
