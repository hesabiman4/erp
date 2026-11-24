import {closeDocumentOrDialog} from './navigation';
import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';

test.setTimeout(180000);
test('multi-day capacity work is previewed, reserved and reviewed on desktop and phone',async({page})=>{
 test.skip(process.env.ERP_DEMO_E2E!=='1','Planning fixtures require the explicitly isolated QA database.');
 const base=process.env.ERP_E2E_BASE_URL||'http://127.0.0.1:5174';expect(base).toContain(':5174');
 const secrets=JSON.parse(await readFile(process.env.ERP_E2E_CREDENTIALS||'../.local/verify_ui_20261029-credentials.json','utf8'));
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base);await page.locator('input[name=username]').fill('owner');await page.locator('input[name=password]').fill(secrets.owner);await page.locator('button[type=submit]').click();await expect(page.locator('.sidebar')).toBeVisible();
 await page.locator('.calendar-select').selectOption('gregorian');const business=await page.locator('.business-switch select').inputValue();
 const fixture=await page.evaluate(async(business)=>{
  const headers={'X-Business-ID':business};const catalogResponse=await fetch('/api/catalog/',{headers});if(!catalogResponse.ok)throw new Error('Catalog unavailable');const catalog=await catalogResponse.json();
  const warehouse=catalog.warehouses.find((w:any)=>w.kind==='store');const product=catalog.products.find((p:any)=>p.kind==='finished'&&p.unit==='cm');if(!warehouse||!product)throw new Error('QA catalog lacks production fixtures');
  const csrf=decodeURIComponent(document.cookie.split('; ').find(row=>row.startsWith('csrftoken='))?.split('=')[1]||'');
  const date=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kabul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const response=await fetch('/api/operations/work_center/',{method:'POST',headers:{...headers,'X-CSRFToken':csrf,'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({date,location:warehouse.location,name:`QA capacity ${crypto.randomUUID()}`,daily_minutes:'120'})});
  const data=await response.json();if(!response.ok)throw new Error(`Center fixture failed${response.status}`);return {warehouse,product,center:data.document.result.work_center};
 },business);
 await page.goto(base+'/operations?view=advanced_planning');await page.getByRole('button',{name:'برنامه چندروزه جدید',exact:true}).click();const dialog=page.getByRole('dialog');
 await dialog.locator('select[name=warehouse]').selectOption(String(fixture.warehouse.id));await dialog.locator('select[name=product]').selectOption(String(fixture.product.id));
 await dialog.locator('input[name=planned_quantity]').fill('100');await dialog.locator('input[name=planned_minutes]').fill('300');await dialog.locator('input[name=stage-minutes-0]').fill('300');await dialog.locator('select[name=stage-center-0]').selectOption(String(fixture.center));
 await dialog.getByRole('button',{name:'محاسبه ظرفیت',exact:true}).click();await expect(dialog.locator('.cut-plan-preview tbody tr')).toHaveCount(3);await expect(dialog.getByRole('button',{name:'ثبت رزرو ظرفیت',exact:true})).toBeEnabled();
 await page.screenshot({path:'../.local/design/advanced-planning-preview.png',fullPage:true});
 const posted=page.waitForResponse(r=>r.url().endsWith('/api/operations/capacity_work_order/')&&r.request().method()==='POST');await dialog.getByRole('button',{name:'ثبت رزرو ظرفیت',exact:true}).click();const response=await posted;const data=await response.json();expect(response.status(),JSON.stringify(data)).toBe(201);expect(data.document.result.slots).toHaveLength(3);expect(data.document.result.stock_posted).toBe(false);
 await expect(page.locator('.document-view')).toBeVisible();await closeDocumentOrDialog(page);await expect(page.locator('.advanced-planning')).toContainText(data.document.number);
 await page.getByRole('tab',{name:'تحلیل تولید واقعی',exact:true}).click();await expect(page.locator('.advanced-planning')).toContainText('تبدیل کیلوگرام مواد به سانتی‌متر محصول انجام نمی‌شود.');
 await page.screenshot({path:'../.local/design/advanced-planning-yield.png',fullPage:true});await page.setViewportSize({width:390,height:844});await page.goto(base+'/operations?view=advanced_planning');await expect(page.locator('.advanced-planning')).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
 await page.screenshot({path:'../.local/design/advanced-planning-phone.png',fullPage:true});expect(errors).toEqual([]);
});
