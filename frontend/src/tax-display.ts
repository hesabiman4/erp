/** Exact presentation for tax schedules; storage and legacy formatting are untouched. */
import Decimal from 'decimal.js';

/** The API keeps original error evidence; show only its translated message here. */
export function taxError(error:unknown):unknown {
 const detail=(error as {detail?:{error?:unknown,translation_complete?:boolean}}|null)?.detail;
 return detail?.translation_complete===true&&typeof detail.error==='string'?new Error(detail.error,{cause:error}):error;
}

function digits(value:string,language:string){return language.startsWith('en')?value:value.replace(/\d/g,d=>'۰۱۲۳۴۵۶۷۸۹'[Number(d)]);}

export function taxNumber(value:unknown,language:string,places=6){
 if(value===null||value===undefined||value==='')return '—';
 try{
  const amount=new Decimal(String(value));if(!amount.isFinite())return '—';
  const [integer,fraction]=amount.toDecimalPlaces(places,Decimal.ROUND_HALF_UP).toFixed().split('.');
  const english=language.startsWith('en');const grouped=integer.replace(/\B(?=(\d{3})+(?!\d))/g,english?',':'٬');
  return digits(grouped+(fraction?(english?'.':'٫')+fraction:''),language);
 }catch{return '—';}
}

export function taxDate(value:unknown,language:string,calendar:'jalali'|'gregorian',monthNames:string[]){
 if(!value)return '—';
 try{
  const raw=String(value),timestamp=raw.includes('T');const instant=new Date(timestamp?raw:raw.slice(0,10)+'T12:00:00Z');
  const parts=new Intl.DateTimeFormat('en-US-u-nu-latn',{calendar:calendar==='jalali'?'persian':'gregory',timeZone:'Asia/Kabul',year:'numeric',month:'numeric',day:'numeric'}).formatToParts(instant);
  const part=(type:string)=>parts.find(p=>p.type===type)?.value||'';
  const date=calendar==='jalali'?`${part('day')} ${monthNames[Number(part('month'))-1]} ${part('year')}`:`${part('year')}/${part('month').padStart(2,'0')}/${part('day').padStart(2,'0')}`;
  const time=timestamp?' · '+new Intl.DateTimeFormat('en-GB-u-nu-latn',{timeZone:'Asia/Kabul',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(instant):'';
  return digits(date+time,language);
 }catch{return '—';}
}
