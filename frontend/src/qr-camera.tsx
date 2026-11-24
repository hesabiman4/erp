import {useEffect,useRef,useState} from 'react';
import {Camera} from 'lucide-react';
import {l} from './localize';

// Frames stay on this device; only a decoded code reaches the scoped lookup API.
export function QRCamera({onCode,onError}:{onCode:(value:string)=>void;onError:(value:string)=>void}){
 const[active,setActive]=useState(false);const[busy,setBusy]=useState(false);const video=useRef<HTMLVideoElement>(null);const stream=useRef<MediaStream|null>(null);const timer=useRef<ReturnType<typeof setTimeout>|null>(null);const generation=useRef(0);
 const stop=()=>{generation.current++;stream.current?.getTracks().forEach(t=>t.stop());stream.current=null;if(timer.current)clearTimeout(timer.current);setActive(false);setBusy(false);};
 useEffect(()=>()=>{generation.current++;stream.current?.getTracks().forEach(t=>t.stop());if(timer.current)clearTimeout(timer.current);},[]);
 useEffect(()=>{const hidden=()=>{if(document.hidden)stop();};document.addEventListener('visibilitychange',hidden);return()=>document.removeEventListener('visibilitychange',hidden);},[]);
 const start=async()=>{
  onError('');if(!window.isSecureContext){onError(l('اسکن دوربین به HTTPS معتبر نیاز دارد. در شبکه HTTP از کد دستی یا اسکنر کیبوردی استفاده کنید.'));return;}
  const id=++generation.current;setBusy(true);
  try{
   const media=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1280}},audio:false});
   if(id!==generation.current){media.getTracks().forEach(t=>t.stop());return;}stream.current=media;setActive(true);
   const {default:decode}=await import('jsqr');const canvas=document.createElement('canvas');const context=canvas.getContext('2d',{willReadFrequently:true});if(!context)throw Error('Canvas unavailable');
   const scan=async()=>{
    if(id!==generation.current)return;
    const element=video.current;
    if(element&&element.srcObject!==media){element.srcObject=media;await element.play();}
    if(id!==generation.current)return;
    if(element&&element.readyState>=2&&element.videoWidth){
     const scale=Math.min(1,800/element.videoWidth);canvas.width=Math.round(element.videoWidth*scale);canvas.height=Math.round(element.videoHeight*scale);context.drawImage(element,0,0,canvas.width,canvas.height);
     const pixels=context.getImageData(0,0,canvas.width,canvas.height);const value=decode(pixels.data,pixels.width,pixels.height,{inversionAttempts:'attemptBoth'})?.data;
     if(value){stop();onCode(value);return;}
    }
    timer.current=setTimeout(()=>{scan().catch(()=>{stop();onError(l('دوربین در دسترس نیست. از HTTPS یا مرورگر مجاز استفاده کنید، یا کد را وارد کنید.'));});},300);
   };setBusy(false);await scan();
  }catch{if(id===generation.current){stop();onError(l('دوربین در دسترس نیست. از HTTPS یا مرورگر مجاز استفاده کنید، یا کد را وارد کنید.'));}}
 };
 return <><button className="button secondary" type="button" disabled={busy} onClick={active?stop:start}><Camera size={18}/>{l(active?'بستن دوربین':'اسکن با دوربین')}</button>{active&&<video ref={video} className="scan-video" playsInline muted/>}</>;
}
