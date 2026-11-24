import {useResource,useScope} from './App';
import type {Row} from './api';
import {ErrorNotice} from './ui';
import {l} from './localize';
const monetary=new Set(['receipt','supplier_payment','supplier_refund','customer_refund','expense_post','cash_transfer','cash_count','opening_cash','employee_advance','payroll_settle','asset_acquire','internal_settlement','bank_reconcile','cash_drawer','statement_import','fx_settle','fx_exchange','fx_remit_dispatch','fx_deposit','fx_refund']);
export function MoneyRouting({action,value,onChange}:{action:string,value:Row,onChange:(value:Row)=>void}){
 const{catalog}=useScope();const enabled=monetary.has(action);const q=useResource('/api/money-instruments/?choices=1',enabled);
 if(!enabled||!q.data?.results?.some((r:Row)=>!r.legacy))return q.isError?<ErrorNotice error={q.error}/>:null;
 const transfer=action==='cash_transfer'||action==='internal_settlement';const keys=transfer?['from_instrument','to_instrument']:action==='statement_import'||action==='bank_reconcile'?['bank_instrument']:action==='cash_drawer'||action==='cash_count'?['cash_instrument']:['cash_instrument','bank_instrument'];
 return <section className="money-routing"><p className="form-info">{l('وقتی چند حساب در یک محل است، حساب واقعی را انتخاب کنید. انتخاب باید با محل و نوع پرداخت یکسان باشد.')}</p><div className="form-grid">{keys.map(key=><label className="field" key={key}><span>{l(({cash_instrument:'صندوق مستقل',bank_instrument:'حساب بانکی مستقل',from_instrument:'حساب مبدأ',to_instrument:'حساب مقصد'} as Row)[key])}</span><select name={key} value={value[key]||''} onChange={event=>onChange({...value,[key]:event.target.value||undefined})}><option value="">{l('انتخاب خودکار فقط در صورت یک حساب')}</option>{q.data.results.filter((row:Row)=>transfer||row.kind===(key==='bank_instrument'?'BANK':'CASH')).map((row:Row)=><option key={row.id} value={row.id}>{catalog.locations?.find((loc:Row)=>loc.id===row.location)?.name} · {row.name} · {row.code}{row.legacy?' · '+l('مانده قبلی'):''}</option>)}</select></label>)}</div></section>;
}
