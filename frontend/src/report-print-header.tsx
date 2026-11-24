import {useScope} from './App';
import {formatCalendarDate} from './calendar';
import {today} from './api';
import {l} from './localize';

/** A report's business, scope and actual date range must survive printing. */
export function ReportPrintHeader({title,from,to,businessWide=false}:{title:string,from?:string,to?:string,businessWide?:boolean}){
 const{business,catalog,locationId}=useScope();
 const location=catalog.locations?.find((row:{id:number,name:string})=>String(row.id)===locationId)?.name;
 return <header className="report-print-header"><div><h2>{business.name}</h2><h3>{l(title)}</h3><p>{businessWide?l('تمام کسب‌وکار'):location||l('تمام موقعیت‌های مجاز')} · {business.currency||'AFN'}</p></div><div className="report-print-dates"><span>{from?formatCalendarDate(from):l('از آغاز')} — {formatCalendarDate(to||today())}</span><small>{l('زمان چاپ')}: {formatCalendarDate(today())}</small></div></header>;
}
