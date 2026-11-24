import i18n from './i18n';
import {publicErrorMessage} from './error-display';
export type Row = Record<string, any>;
export class ApiError extends Error { status:number; detail:unknown; constructor(message:string,status:number,detail:unknown){ super(message);this.status=status;this.detail=detail; } }
function cookie(name:string){return document.cookie.split('; ').find(x=>x.startsWith(`${name}=`))?.split('=').slice(1).join('=') || '';}
let businessId='',locationId='',cashReason='';
export function configureScope(business:string,location=''){if(businessId!==business)cashReason='';businessId=business;locationId=location;}
export function configureCashReason(reason:string){cashReason=reason;}
export async function request<T=Row>(path:string,options:RequestInit={}):Promise<T>{let response:Response;try{response=await fetch(path,{...options,credentials:'same-origin',headers:{...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),'Accept-Language':i18n.language,'X-CSRFToken':decodeURIComponent(cookie('csrftoken')),...(businessId?{'X-Business-ID':businessId}:{}),...(locationId?{'X-Location-ID':locationId}:{}),...(cashReason&&options.method==='POST'&&path.startsWith('/api/operations/')?{'X-Cash-Reason':encodeURIComponent(cashReason)}:{}),...options.headers}});}catch(error){throw new ApiError(publicErrorMessage(null,0),0,{cause:error});}const data=await response.json().catch(()=>({detail:response.statusText}));if(!response.ok)throw new ApiError(publicErrorMessage(data,response.status),response.status,data);return data;}
export const api={get:<T=Row>(p:string)=>request<T>(p),post:<T=Row>(p:string,body:unknown,idempotencyKey?:string)=>request<T>(p,{method:'POST',body:JSON.stringify(body),headers:{'Idempotency-Key':idempotencyKey||crypto.randomUUID()}}),patch:<T=Row>(p:string,body:unknown)=>request<T>(p,{method:'PATCH',body:JSON.stringify(body)}),upload:<T=Row>(p:string,body:FormData,key?:string)=>request<T>(p,{method:'POST',body,headers:{'Idempotency-Key':key||crypto.randomUUID()}})};
export function rows(data:unknown):Row[]{if(Array.isArray(data))return data;if(data&&typeof data==='object'){const d=data as Row;return d.results||d.items||d.data||[];}return [];}
export function normalizeDigits(value:string){return value.replace(/[۰-۹]/g,d=>String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d))).replace(/[٠-٩]/g,d=>String('٠١٢٣٤٥٦٧٨٩'.indexOf(d))).replace(/٫/g,'.').replace(/٬/g,'');}
export function number(value:unknown,maximumFractionDigits=2){if(value===null||value===undefined||value==='')return '—';const n=Number(value);if(!Number.isFinite(n))return '—';const lang=i18n.language;return new Intl.NumberFormat(lang==='en'?'en-US':lang==='ps'?'ps-AF':'fa-AF',{maximumFractionDigits}).format(n);}
export const money=(v:unknown)=>number(v)==='—'?'—':`${number(v)} ؋`;
export function today(){return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kabul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());}
