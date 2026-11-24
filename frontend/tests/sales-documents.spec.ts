import {closeDocumentOrDialog} from './navigation';
import {test,expect} from '@playwright/test';
import {readFile,mkdir} from 'node:fs/promises';
const evidence=process.env.ERP_E2E_OUTPUT||'../.local/design/sales-documents';
test.setTimeout(180000);
test.beforeEach(async({page})=>{
 test.skip(process.env.ERP_DEMO_E2E!=='1','Synthetic workflows run only against the separate QA database.');
 expect(process.env.ERP_E2E_BASE_URL).toContain(':5174');
 const credentials=JSON.parse(await readFile(process.env.ERP_E2E_CREDENTIALS||'../.local/verify_ui_20261029-credentials.json','utf8'));
 await page.goto('/');await page.locator('[name=username]').fill('owner');await page.locator('[name=password]').fill(credentials.owner);await page.locator('[type=submit]').click();await expect(page.locator('.today-work')).toBeVisible();await mkdir(evidence,{recursive:true});
});

test('new-entry groups stay inside RTL/LTR workspace and support keyboard and mobile',async({page})=>{
 const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
 for(const language of ['fa','en']){
  await page.locator('.language-select').selectOption(language);
  for(const width of [1348,1024,768,390]){
   await page.setViewportSize({width,height:840});await page.locator('.quick-create>button').click();
   const dialog=page.locator('#global-create-panel');await expect(dialog).toBeVisible();await expect(dialog.locator('section')).toHaveCount(3);
   const bounds=await dialog.boundingBox();const workspace=await page.locator('.main-shell').boundingBox();expect(bounds).toBeTruthy();expect(workspace).toBeTruthy();
   expect(bounds!.x).toBeGreaterThanOrEqual(Math.max(0,workspace!.x));expect(bounds!.x+bounds!.width).toBeLessThanOrEqual(Math.min(width,workspace!.x+workspace!.width));
   for(const section of await dialog.locator('section').all())await expect(section.locator('button').first()).toBeInViewport();
   await expect(dialog.locator('button').first()).toBeFocused();await page.keyboard.press('End');await expect(dialog.locator('button').last()).toBeFocused();await page.keyboard.press('Home');await expect(dialog.locator('button').first()).toBeFocused();
   await page.screenshot({path:`${evidence}/new-menu-${language}-${width}.png`});await closeDocumentOrDialog(page);await expect(dialog).toHaveCount(0);await expect(page.locator('.quick-create>button')).toBeFocused();
  }
 }
 await page.locator('.language-select').selectOption('fa');await page.locator('.quick-create>button').click();await page.locator('#global-create-panel button').first().click();await expect(page.locator('#global-create-panel')).toHaveCount(0);await expect(page.locator('.modal')).toBeVisible();await closeDocumentOrDialog(page);expect(errors).toEqual([]);
});

test('draft quotation can be closed from its document and cannot be posted later',async({page})=>{
 const business=await page.locator('.business-switch select').inputValue();
 const draft=await page.evaluate(async business=>{
  const headers={'X-Business-ID':business,'Content-Type':'application/json','X-CSRFToken':decodeURIComponent(document.cookie.split('; ').find(value=>value.startsWith('csrftoken='))?.split('=')[1]||'')};
  const catalog=await fetch('/api/catalog/',{headers}).then(r=>r.json());
  const product=catalog.products.find((p:any)=>p.kind==='finished');const warehouse=catalog.warehouses.find((w:any)=>w.kind==='store');const customer=catalog.parties.find((p:any)=>p.kind==='customer');
  const response=await fetch('/api/documents/',{method:'POST',headers,body:JSON.stringify({kind:'quotation',data:{date:'2026-11-01',warehouse:warehouse.id,party:customer.id,lines:[{product:product.id,quantity:'2',unit_price:product.price}]}})});
  if(response.status!==201)throw new Error('Draft creation failed');return response.json();
 },business);
 await page.goto('/sales');await page.getByRole('tab',{name:'پیش‌فاکتورها',exact:true}).click();await page.locator('tbody tr').filter({hasText:draft.number}).click();
 await expect(page.locator('.sales-flow-panel')).toContainText('پیش‌نویس');await page.locator('.sales-flow-actions button.secondary').click();await expect(page.locator('.modal select[name=order]')).toHaveValue(String(draft.id));
 await page.locator('.modal input[name=reason]').fill('QA abandoned proposal before posting');const closed=page.waitForResponse(r=>r.url().endsWith('/api/operations/order_cancel/')&&r.request().method()==='POST');await page.locator('.modal [type=submit]').click();const response=await closed;expect(response.status()).toBe(201);const cancellation=await response.json();await expect(page).toHaveURL(new RegExp(`/documents/${cancellation.document.id}\\?`));await expect(page.locator('.modal select[name=order]')).toHaveCount(0);await expect(page.locator('.document-detail-page .document-view')).toBeVisible();await closeDocumentOrDialog(page);await expect(page.locator('.modal')).toHaveCount(0);await expect(page.locator('.document-detail-page')).toBeVisible();await closeDocumentOrDialog(page);
 await page.locator('tbody tr').filter({hasText:draft.number}).click();await expect(page.locator('.sales-flow-panel')).toContainText('لغوشده');await expect(page.locator('.sales-flow-actions button')).toHaveCount(0);await expect(page.locator('.document-actions button.primary')).toHaveCount(0);
 await page.screenshot({path:`${evidence}/cancelled-draft.png`});
 const printed=await page.request.get(`/api/documents/${draft.id}/print/?business=${business}`);expect(printed.status()).toBe(200);expect(await printed.text()).toContain('cancelled before posting');
});
