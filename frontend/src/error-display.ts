import i18n from './i18n';

const copy:Record<string,[string,string,string]>={
 request:['درخواست تکمیل نشد. معلومات واردشده را بررسی کنید و دوباره کوشش کنید.','غوښتنه بشپړه نه شوه. لیکل شوي معلومات وګورئ او بیا هڅه وکړئ.','The request could not be completed. Review the entered information and try again.'],
 network:['اتصال به سیستم برقرار نشد. اتصال را بررسی کنید؛ پیش از ثبت دوباره، وضعیت سند را ببینید.','له سیستم سره اړیکه ټینګه نه شوه. اړیکه وګورئ؛ له بیا ثبتولو مخکې د سند حالت وګورئ.','Could not reach the system. Check the connection and document status before submitting again.'],
 denied:['صلاحیت انجام این کار را ندارید یا نشست شما پایان یافته است. دسترسی خود را بررسی کنید.','د دې کار اجازه نه لرئ یا ناسته پای ته رسېدلې ده. خپله اجازه وګورئ.','Access was denied or your session has expired. Check your access.'],
 server:['سیستم درخواست را تکمیل کرده نتوانست. پیش از تلاش دوباره، وضعیت سند را بررسی کنید.','سیستم غوښتنه بشپړه نه کړه. له بیا هڅې مخکې د سند حالت وګورئ.','The system could not complete the request. Check the document status before trying again.'],
 conflict:['این ریکارد تغییر کرده یا قبلاً ثبت شده است. صفحه و سند مربوط را بررسی کنید.','دا ریکارډ بدل شوی یا مخکې ثبت شوی دی. پاڼه او اړوند سند وګورئ.','This record has changed or already exists. Review the page and related document.'],
};
const text=(key:string)=>copy[key][i18n.language.startsWith('en')?2:i18n.language.startsWith('ps')?1:0];
const technical=/(?:error_original|error_code|error_language|translation_complete|\[object Object\]|Traceback|<\/?(?:html|script|body)|(?:^|\n)\s*(?:at |File "))/i;
const safe=(value:unknown)=>typeof value==='string'&&value.length<=2000&&!technical.test(value);
const translated=(value:string)=>String(i18n.t(value,{keySeparator:false,defaultValue:value}));

/** Select staff-facing copy only. Never flatten an API diagnostic envelope. */
export function publicErrorMessage(data:unknown,status=400):string{
 const fallback=()=>text(status===0?'network':status>=500?'server':status===401||status===403?'denied':status===409?'conflict':'request');
 if(data&&typeof data==='object'&&!Array.isArray(data)){
  const body=data as Record<string,unknown>;
  const original=body.error_original as Record<string,unknown>|undefined;
  const primary=body.error||body.detail;
  if(safe(primary)&&body.error_language===i18n.language.split('-')[0]&&original&&(original.error||original.detail)!==primary)return String(primary);
  // A complete server translation is the authoritative primary validation message.
  if(body.translation_complete===true){
   if(safe(primary))return String(primary);
   const values=collect(body.details||body);
   if(values.length)return [...new Set(values)].join('، ');
  }
  // Older endpoints can return a single known/local-language message without metadata.
  if(!('translation_complete' in body))return publicErrorMessage(body.error||body.detail,status);
  return fallback();
 }
 if(safe(data)){
  const value=translated(String(data));
  if(i18n.language.startsWith('en')||value!==data||/[\u0600-\u06ff]/.test(value))return value;
 }
 return fallback();
}
function collect(value:unknown,depth=0):string[]{
 if(depth>5)return [];
 if(safe(value))return [String(value)];
 if(Array.isArray(value))return value.flatMap(v=>collect(v,depth+1));
 if(value&&typeof value==='object')return Object.entries(value).filter(([key])=>!['error_original','error_code','error_language','translation_complete','error_summary'].includes(key)).flatMap(([,v])=>collect(v,depth+1));
 return [];
}
export function friendlyError(error:unknown):string{
 if(error instanceof Error)return publicErrorMessage(error.message,(error as Error&{status?:number}).status??400);
 return publicErrorMessage(error);
}
