/** Build the Afghan Dari edition with Chromium's native Arabic shaping and RTL.
 * Requires the repository's frontend Playwright install and Microsoft Edge.
 * No database access. Rebuild: node scripts/build_dari_accounting_manual_pdf.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import crypto from 'node:crypto';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const require=createRequire(path.join(root,'frontend/package.json'));
const {chromium}=require('@playwright/test');
const source=path.join(root,'docs/CHART_OF_ACCOUNTS_BEGINNER_MANUAL_PASHTO.md');
const output=path.join(root,'output/pdf/Nawa_Beginner_Accounting_Manual_Pashto.pdf');
const evidence=path.join(root,'.local/design/pdf-manual-pashto');
fs.mkdirSync(evidence,{recursive:true});fs.mkdirSync(path.dirname(output),{recursive:true});
const text=fs.readFileSync(source,'utf8');
const esc=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
function inline(s){
 const tokens=[];
 s=s.replace(/(?<=\p{L})(?=[۰-۹])|(?<=[۰-۹])(?=\p{L})/gu,' ');
 s=s.replace(/`([^`]+)`/g,(_,v)=>{tokens.push(`<code dir="ltr">${esc(v)}</code>`);return `TOKEN${tokens.length-1}END`;});
 s=s.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,(_,label,url)=>{tokens.push(`<a href="${esc(url)}">${esc(label)}</a>`);return `TOKEN${tokens.length-1}END`;});
 s=s.replace(/\b(?:Dr|Cr)\s+[A-Z_]+(?:\s+\d+(?:[.,]\d+)?)?(?:\s*[/;]\s*(?:Dr|Cr)\s+[A-Z_]+(?:\s+\d+(?:[.,]\d+)?)?)*/g,v=>{tokens.push(`<bdi dir="ltr">${esc(v)}</bdi>`);return `TOKEN${tokens.length-1}END`;});
 s=esc(s).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
 s=s.replace(/TOKEN(\d+)END/g,(_,n)=>tokens[+n]);
 return s;
}
const chapters=[...text.matchAll(/^## (.+)$/gm)].map(m=>m[1]);
const codes=[...text.matchAll(/^\| \d{5} · `([^`]+)`/gm)].map(m=>m[1]);
const actions=[...text.matchAll(/^\| `([a-z_]+)` \|/gm)].map(m=>m[1]);
if(chapters.length!==11||codes.length<62||actions.length<96||new Set(codes).size!==codes.length||new Set(actions).size!==actions.length)throw Error(`Incomplete source ${chapters.length}/${codes.length}/${actions.length}`);
function figure(title,boxes,note){return `<figure><figcaption>${title}</figcaption><div class="diagram">${boxes.map(([head,body])=>`<div><strong>${head}</strong><p>${body}</p></div>`).join('')}</div><p class="figure-note">${note}</p></figure>`;}
const figures={
1:figure('۱. د حسابدارۍ معادله',[['شتمنۍ','نغدې + مواد + محصول'],['پورونه','عرضه کوونکو ته پور'],['د مالک پانګه','پانګه + ګټه']],'شتمنۍ = پورونه + د مالک پانګه؛ هر ثبت باید برابر وي.'),
4:figure('۲. د واقعي تولید د لګښت بهیر',[['خام مواد','20,000 AFN'],['روان تولید','20,000 + 3,000 + 2,000 = 25,000 AFN'],['بشپړ محصول','100 cm · 250 AFN/cm']],'د 10cm پلور لګښت2,500؛ پاتې90cm ارزښت22,500 افغانۍ.')+figure('۳. د مثال وروستی بیلانس',[['شتمنۍ','222,500 AFN'],['پورونه','20,000 AFN'],['د مالک پانګه','202,500 AFN']],'222,500 = 20,000 + 202,500؛ ګټه2,500 ده.'),
6:figure('۴. یو بل او دوه رسیدونه',[['د پلور بل','5,000 AFN'],['لومړی رسید','3,500 AFN'],['دویم رسید','1,500 AFN']],'پلور5,000 پاتې کېږي؛ وروستی طلب صفر دی.')+figure('۵. معاش او مخکې ورکړه جلا حسابونه دي',[['د معاش پور','10,000 − 6,000 − 2,000 = 2,000'],['مخکې ورکړه','3,500 − 2,000 = 1,500']],'د مخکې ورکړې کسر نوې نغدي ورکړه نه ده.'),
8:figure('۶. د اسعارو مقدار او افغاني ارزښت',[['اصلي ثبت','USD100 ×70 =7,000 AFN'],['بیا ارزونه','USD100 ×72 =7,200 AFN'],['د USD40 رسید','40 ×73 =2,920 AFN']],'مقدار او افغاني ارزښت جلا دي؛ نرخونه یوازې تعلیمي مثالونه دي.')};
const lines=text.split(/\r?\n/);let content='',preface='',chapter=0;
for(let i=0;i<lines.length;){let line=lines[i].trim();if(!line||line.startsWith('# ')){i++;continue;}
 if(line.startsWith('## ')){chapter++;content+=`<h1 id="chapter-${chapter}">${inline(line.slice(3))}</h1>${figures[chapter]||''}`;i++;continue;}
 if(line.startsWith('### ')){content+=`<h2>${inline(line.slice(4))}</h2>`;i++;continue;}
 if(line.startsWith('|')){
  const table=[];while(i<lines.length){if(lines[i].trim().startsWith('|')){table.push(lines[i].trim().slice(1,-1).split('|').map(x=>x.trim()));i++;}else if(!lines[i].trim()&&lines[i+1]?.trim().startsWith('|')){i++;}else break;}
  const headers=table.shift();const rows=table.filter(row=>!row.every(x=>/^:?-+:?$/.test(x.replaceAll(' ',''))));
  if(headers[0]==='شمېره / کوډ'||headers[0]==='عملیات'){
   const account=headers[0]==='شمېره / کوډ';
   for(const row of rows){content+=`<article class="reference-card"><header><h3>${inline(row[0])}${account?' · '+inline(row[1]):''}</h3>${account?'':`<p>${inline(row[1])}</p>`}</header><div class="card-body"><section><h4>${headers[2]}</h4><p>${inline(row[2])}</p></section><section><h4>${headers[3]}</h4><p>${inline(row[3])}</p></section></div></article>`;}
  }else if(headers[0]==='پړاو'){
   rows.forEach(row=>content+=`<article class="step"><h3>مرحلهٔ ${row[0]} · ${inline(row[1])}</h3><div class="journal"><div><h4>بدهکار</h4><p dir="ltr">${esc(row[2])}</p></div><div><h4>بستانکار</h4><p dir="ltr">${esc(row[3])}</p></div></div><p>${inline(row[4])}</p></article>`);
   content+=figure('۳. بیلانس نهایی مثال تولید',[
    ['دارایی: ۲۲۲۵۰۰','نقد۱۷۰۰۰۰ + مواد۳۰۰۰۰ + محصول۲۲۵۰۰'],['بدهی و حقوق مالک: ۲۲۲۵۰۰','تأمین‌کننده۲۰۰۰۰ + سرمایه۲۰۰۰۰۰ + مفاد۲۵۰۰']], 'مفاد: فروش۵۰۰۰ − بهای فروش۲۵۰۰ = ۲۵۰۰ افغانی. نقد با مفاد یک چیز نیست.');
  }else{content+=`<table><thead><tr>${headers.map(x=>`<th>${inline(x)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(x=>`<td>${inline(x)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;}
  continue;
 }
 const paragraph=[line];i++;while(i<lines.length&&lines[i].trim()&&!/^(#|\||- )/.test(lines[i].trim()))paragraph.push(lines[i++].trim());
 const block=`<p${line.startsWith('- ')?' class="reference"':''}>${inline(paragraph.join(' '))}</p>`;
 if(chapter===0)preface+=block;else content+=block;
}
const font=name=>`data:font/woff2;base64,${fs.readFileSync(path.join(root,`frontend/node_modules/@fontsource/vazirmatn/files/vazirmatn-arabic-${name}-normal.woff2`)).toString('base64')}`;
const html=`<!doctype html><html lang="ps-AF" dir="rtl"><head><meta charset="utf-8"><title>نوا - د حسابدارۍ پښتو لارښود</title><style>
@font-face{font-family:Vazirmatn;src:url('${font(400)}')}@font-face{font-family:Vazirmatn;src:url('${font(700)}');font-weight:700}
@page{size:A4;margin:19mm 16mm 19mm}*{box-sizing:border-box}body{margin:0;color:#243c50;font:10pt/1.95 Vazirmatn,Arial,sans-serif}h1,h2,h3,h4,p{margin:0}p{margin:0 0 3mm}h1{font-size:21pt;line-height:1.7;color:#142b43;margin:0 0 7mm;break-before:page;break-after:avoid}h2{font-size:13pt;color:#087f78;margin:6mm 0 3mm;break-after:avoid}h3{font-size:11pt;color:#142b43;line-height:1.8}h4{font-size:8.5pt;color:#087f78;margin-bottom:1mm}strong{font-weight:700}code{font-family:Arial,sans-serif;font-size:8.7pt;color:#087f78;display:inline-block;unicode-bidi:isolate;overflow-wrap:anywhere}bdi{unicode-bidi:isolate}a{color:#087f78;text-decoration:none}table{width:100%;border-collapse:collapse;margin:4mm 0 6mm;font-size:9pt;line-height:1.9;table-layout:fixed}thead{display:table-header-group}th{background:#142b43;color:white;text-align:right}td,th{padding:2.8mm;border-bottom:.2mm solid #d9e4eb;vertical-align:top;overflow-wrap:anywhere}tr:nth-child(even) td{background:#f4f8fa}tr{break-inside:avoid}table th:first-child{width:25%}.reference-card,.step{border:.25mm solid #d9e4eb;border-radius:2mm;margin-bottom:4mm;break-inside:avoid;overflow:hidden}.reference-card header{background:#eff7f5;padding:3mm 4mm}.reference-card header p{margin:0;color:#5b7081;font-size:9pt}.card-body,.journal{display:flex}.card-body>section{width:50%;padding:3mm 4mm}.card-body>section+section{border-right:.2mm solid #d9e4eb}.card-body p{font-size:9.3pt;margin:0;line-height:1.9}.step{padding:4mm}.step h3{margin-bottom:3mm}.step>p{margin:3mm 0 0;font-size:9.5pt}.journal{gap:4mm;background:#f4f8fa;padding:3mm}.journal>div{width:50%}.journal p{font:9pt/1.6 Arial,sans-serif;margin:0;text-align:left}.cover{min-height:246mm;background:#142b43;color:white;padding:15mm 10mm;position:relative;break-after:page;border-top:4mm solid #087f78}.cover .brand{font:700 11pt Arial;color:#8ed9ce;letter-spacing:2px;text-align:left}.cover h1{color:white;font-size:34pt;line-height:1.65;break-before:auto;margin-top:28mm;margin-bottom:7mm}.cover .subtitle{font-size:16pt;color:#b8e1db}.cover .intro{margin-top:10mm;color:#d6e4ec;font-size:12pt}.cover .stats{display:flex;gap:4mm;margin-top:24mm}.cover .stats div{flex:1;background:#203e56;padding:5mm 3mm;text-align:center;border-radius:2mm}.cover .stats b{display:block;font:700 22pt Arial;margin-bottom:3mm}.cover .edition{margin-top:16mm;font-size:9pt;color:#c5d7e4}.navigation{break-after:page}.navigation h1{break-before:auto;margin-top:3mm}.navigation a{display:block;border-bottom:.2mm solid #d9e4eb;padding:2.3mm 0;font-size:10.5pt}.intro-note{padding:4mm;background:#eff7f5;border-right:1mm solid #087f78;margin:5mm 0}figure{margin:0 0 6mm;padding:5mm;background:#f4f8fa;border:.25mm solid #d9e4eb;border-radius:3mm;break-inside:avoid}figcaption{font-size:11pt;color:#087f78;font-weight:700;margin-bottom:4mm}.diagram{display:flex;gap:3mm}.diagram>div{flex:1;background:white;border:.2mm solid #d9e4eb;border-top:1mm solid #087f78;border-radius:2mm;padding:3mm;text-align:center;min-width:0}.diagram strong{font-size:10pt;line-height:1.9;display:block;color:#142b43}.diagram p{font-size:9pt;margin:2mm 0 0}.diagram bdi{font-family:Arial,sans-serif;white-space:nowrap;font-size:9pt}.figure-note{margin:4mm 0 0;font-size:9pt}.reference{font-size:9pt;overflow-wrap:anywhere}
table{font-size:8.8pt;line-height:1.75}td,th{padding:2.3mm}</style></head><body><section class="cover"><div class="brand">NAWA / MANUFACTURING & ACCOUNTING</div><h1>د حسابونو لارښود<br>د نویو کاروونکو لپاره</h1><p class="subtitle">پښتو · عملي مثالونه</p><p class="intro">مواد، تولید، پلور او ګټه وپېژنئ؛<br>د هرې چارې اغېز په اړوند حساب کې وګورئ.</p><div class="stats"><div><b>${codes.length}</b>قالب حسابونه</div><div><b>${actions.length}</b>د سیستم چارې</div><div><b>AFN</b>تعلیمي مثالونه</div></div><p class="edition">۲۲ نومبر۲۰۲۶<br>تعلیمي لارښود؛ د واقعي سوداګرۍ معلومات نه دي.</p></section><section class="navigation"><h1>کارول او لړلیک</h1><p>لومړی بنسټیزې برخې او د تولید بشپړ مثال ولولئ؛ بیا حسابونه او عملیاتي کوډونه د ورځنۍ مرجع په توګه وکاروئ.</p><p class="intro-note">د اسفنج۴۵ کیلوګرام نوم سوداګریزه درجه ده، وزن یا کثافت نه دی. اسفنج په مناسبې اندازې د لوړوالي سانتي مترو او سریښ په کیلوګرام پلورل کېږي.</p>${chapters.map((title,n)=>`<a href="#chapter-${n+1}">${inline(title)}</a>`).join('')}<div style="margin-top:5mm;font-size:8.3pt;line-height:1.9">${preface}</div></section>${content}</body></html>`;
const htmlPath=path.join(evidence,'manual.html');fs.writeFileSync(htmlPath,html);
const browser=await chromium.launch({channel:'msedge',headless:true});
try{const page=await browser.newPage();await page.goto(pathToFileURL(htmlPath).href);await page.evaluate(()=>document.fonts.ready);await page.emulateMedia({media:'print'});
 await page.pdf({path:output,format:'A4',printBackground:true,preferCSSPageSize:true,displayHeaderFooter:true,tagged:true,outline:true,headerTemplate:'<div style="font-size:8px;color:#587182;width:100%;margin:0 16mm;display:flex;justify-content:space-between"><span>NAWA · ACCOUNTING GUIDE</span><span>PASHTO · 2026-11-22</span></div>',footerTemplate:'<div style="font-size:8px;color:#587182;width:100%;margin:0 16mm;display:flex;justify-content:space-between"><span>Training examples · AFN</span><span class="pageNumber"></span></div>'});
 fs.writeFileSync(path.join(evidence,'verification.json'),JSON.stringify({pdf:output,source,source_sha256:crypto.createHash('sha256').update(text).digest('hex'),chapters:chapters.length,accounts:codes.length,operations:actions.length,figures:6,renderer:'Chromium native RTL with embedded Vazirmatn',translation_review:'Pashto authored; native accountant/editor review pending'},null,2));console.log(output);
}finally{await browser.close();}

