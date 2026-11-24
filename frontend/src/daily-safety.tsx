import {createContext,useCallback,useContext,useEffect,useRef,useState} from 'react';
import type {ReactNode} from 'react';
import {Modal} from './ui';
import {l} from './localize';
import {CalendarContext,displayValue} from './calendar';
type Review={title:string,message:string,details?:[string,string][]};
const ReviewContext=createContext<(review:Review)=>Promise<boolean>>(async()=>false);
const CancelReviewContext=createContext<()=>void>(()=>{});
export const useReview=()=>useContext(ReviewContext);
export function ReviewScope({scopeKey}:{scopeKey:string}){const cancel=useContext(CancelReviewContext);useEffect(()=>{cancel();return cancel;},[scopeKey,cancel]);return null;}
export function ReviewProvider({children}:{children:ReactNode}){
 const calendar=useContext(CalendarContext);
 const[current,setCurrent]=useState<Review|null>(null);const resolve=useRef<((answer:boolean)=>void)|undefined>(undefined);
 const close=useCallback((answer:boolean)=>{resolve.current?.(answer);resolve.current=undefined;setCurrent(null);},[]);
 const cancel=useCallback(()=>close(false),[close]);
 return <CancelReviewContext.Provider value={cancel}><ReviewContext.Provider value={review=>new Promise<boolean>(done=>{if(resolve.current)resolve.current(false);resolve.current=done;setCurrent(review);})}>{children}{current&&<Modal title={l(current.title)} onClose={()=>close(false)}><div className="review-action"><p>{l(current.message)}</p>{current.details&&<dl>{current.details.map(([key,value])=><div key={key}><dt>{l(key)}</dt><dd><bdi>{displayValue(value,calendar)}</bdi></dd></div>)}</dl>}<p className="form-info">{l('ثبت نهایی با قواعد عادی حسابداری انجام می‌شود. اسناد ثبت‌شده با برگشت یا اصلاح مجاز تصحیح می‌شوند.')}</p><div className="action-row"><button className="button secondary" onClick={()=>close(false)}>{l('انصراف')}</button><button className="button primary" onClick={()=>close(true)}>{l('تأیید و ادامه')}</button></div></div></Modal>}</ReviewContext.Provider></CancelReviewContext.Provider>;
}
