import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {useScope,hasPermission} from './App';
import {api,number,money,rows} from './api';
import {DataTable,ErrorNotice,Spinner} from './ui';
import type {TableQuery,TableFilter,Column} from './data-table';
import {l} from './localize';

export function InventoryRegister(){const{businessId,locationId,userId}=useScope();return <Register key={[businessId,locationId,userId].join(':')}/>;}
function Register(){
 const{businessId,locationId,userId,business,catalog}=useScope();const[query,setQuery]=useState<TableQuery>({search:'',sort:null,filters:{}});const[offset,setOffset]=useState(0);const costs=hasPermission(business,'cost.view');
 const params=new URLSearchParams({limit:'100',offset:String(offset),q:query.search});
 if(query.sort)params.set('sort',(query.sort.direction==='desc'?'-':'')+query.sort.key);
 for(const[id,value]of Object.entries(query.filters))if(typeof value==='string'&&value)params.set(id,value);
 const q=useQuery({queryKey:['stock-register',businessId,locationId,params.toString()],queryFn:()=>api.get('/api/stock-register/?'+params),placeholderData:previous=>previous});
 const filters:TableFilter[]=[{id:'warehouse',label:'انبار',type:'choice',persist:true,options:(catalog.warehouses||[]).map((w:any)=>({value:String(w.id),label:w.name})),value:r=>r.warehouse},{id:'availability',label:'موجودی',type:'choice',persist:true,options:[{value:'in_stock',label:'دارای موجودی'},{value:'empty',label:'بدون موجودی'}],value:r=>r.quantity}];
 const columns:Column[]=[{key:'product',label:'محصول',render:r=>r.product_name},{key:'warehouse',label:'انبار',render:r=>catalog.warehouses?.find((w:any)=>w.id===r.warehouse)?.name||r.warehouse_name},{key:'profile',label:'اندازه / مشخصه'},{key:'quantity',label:'مقدار',sortType:'decimal',render:r=><bdi>{number(r.quantity,6)} {r.unit}</bdi>}];
 if(costs)columns.push({key:'value',label:'ارزش موجودی',sortType:'decimal',total:true,render:r=>money(r.value)},{key:'average_cost',label:'بهای واحد',sortType:'decimal',render:r=>money(r.average_cost)});
 const changed=(next:TableQuery)=>{if(JSON.stringify(next)!==JSON.stringify(query)){setQuery(next);setOffset(0);}};
 return <div className="inventory-register">
  {q.isLoading&&<Spinner/>}{q.isError&&<ErrorNotice error={q.error} retry={()=>q.refetch()}/>}
  <div className="summary-strip" aria-live="polite" aria-busy={q.isFetching}><div><span>{l('گروه‌های موجودی مطابق فیلتر')}</span><strong>{q.data?number(q.data.count):'—'}</strong></div>{costs&&<div><span>{l('ارزش تمام موجودی مجاز مطابق فیلتر')}</span><strong>{q.data?money(q.data.totals.value):'—'}</strong></div>}</div>
  {q.isFetching&&q.data&&<p role="status">{l('در حال تازه‌سازی نتایج؛ ارقام قبلی تا پایان بررسی نمایش داده می‌شود.')}</p>}
  <DataTable data={rows(q.data)} columns={columns} tableKey="inventory:pools" preferenceScope={{userId,businessId,locationId}} filters={filters} remote={{onQuery:changed,busy:q.isFetching,searchLabel:'جستجو در تمام موجودی مجاز'}}/>
  {q.data&&q.data.count>100&&<div className="pagination"><span>{number(q.data.offset+1)}–{number(q.data.offset+rows(q.data).length)} {l('از')} {number(q.data.count)}</span><div><button className="button secondary small" disabled={q.isFetching||!offset} onClick={()=>setOffset(Math.max(0,offset-100))}>{l('صفحه قبل')}</button><button className="button secondary small" disabled={q.isFetching||q.data.next_offset===null} onClick={()=>setOffset(q.data!.next_offset)}>{l('صفحه بعد')}</button></div></div>}
  {q.data&&<details className="advanced-actions"><summary>{l('مجموع مقدار بر اساس محصول و اندازه')}</summary><p>{l('مقادیر هر محصول، واحد و اندازه جدا جمع می‌شود؛ این ارقام تضمین مناسب‌بودن قطعات برای یک برش نیست.')}</p><DataTable data={q.data.quantities} columns={[{key:'product__name',label:'محصول'},{key:'profile',label:'اندازه / مشخصه'},{key:'quantity',label:'مقدار',render:r=><bdi>{number(r.quantity,6)} {r.product__unit}</bdi>}]} tools={false}/></details>}
 </div>;
}
