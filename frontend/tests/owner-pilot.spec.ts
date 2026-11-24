import {test,expect} from '@playwright/test';
import {readFile,mkdir} from 'node:fs/promises';
test.setTimeout(180000);
test('owner pilot opens the actual isolated build and each generated role enforces its scope',async({browser,page})=>{
 test.skip(process.env.ERP_OWNER_PILOT!=='1','Only the explicitly enabled isolated owner pilot.');expect(process.env.ERP_E2E_BASE_URL).toBe('http://localhost:8081');const marker=await(await page.request.get('/pilot-info/')).json();expect(marker.synthetic_only).toBe(true);expect(marker.pilot_id).toBe('owner_20261122');
 const folder='../.local/pilots/owner_20261122';const credentials=JSON.parse(await readFile(folder+'/credentials.json','utf8'));const scenario=JSON.parse(await readFile(folder+'/scenario.json','utf8'));const invoice=scenario.events.find((e:any)=>e.step==='permanent-customer-5000-sale');
 await page.goto('/');await page.locator('[name=username]').fill('owner');await page.locator('[name=password]').fill(credentials.owner);await page.locator('[type=submit]').click();await expect(page.locator('.sidebar')).toBeVisible();await expect(page.locator('.business-switch')).toContainText('OWNER TRAINING');await expect(page.locator('.language-select')).toHaveValue('fa');await expect(page.locator('.calendar-select')).toHaveValue('jalali');await expect(page.locator('html')).toHaveAttribute('dir','rtl');await page.goto(invoice.href);await expect(page.locator('.document-detail-page')).toContainText(invoice.number);await expect(page.locator('.document-detail-page')).toContainText('۵٬۰۰۰');await expect(page.locator('.document-snapshot-summary')).toContainText('مانده هنگام ثبت');await expect(page.locator('.document-snapshot-summary')).toContainText('۱٬۵۰۰');await expect(page.locator('.document-summary')).toContainText('۰');await mkdir(folder+'/screenshots',{recursive:true});await page.screenshot({path:folder+'/screenshots/owner-invoice-dari.png',fullPage:true});
 const headers={'X-Business-ID':String(scenario.business)};const original=await(await page.request.get(`/api/documents/${invoice.id}/`,{headers})).json();expect(original.amount).toBe('5000.00');expect(original.balance).toBe('0.00');
 for(const username of ['herat_cashier','kabul_cashier','factory','accountant','furniture']){
  const context=await browser.newContext();const role=await context.newPage();await role.goto('/');await role.locator('[name=username]').fill(username);await role.locator('[name=password]').fill(credentials[username]);await role.locator('[type=submit]').click();await expect(role.locator('.sidebar')).toBeVisible();
  const result=await role.request.get(`/api/documents/${invoice.id}/`,{headers});
  if(['herat_cashier','factory','furniture'].includes(username)){expect(result.status(),username).toBe(403);expect((await role.request.get(`/api/attachments/${scenario.attachment}/`,{headers})).status()).toBe(403);}
  else{expect(result.status(),username).toBe(200);const data=await result.json();if(username==='kabul_cashier')expect(data.result.lines[0]).not.toHaveProperty('cost');}
  if(username==='furniture'){const data=await(await role.request.get('/api/context/')).json();expect(data.businesses.map((b:any)=>b.id)).toEqual([scenario.furniture]);}
  await context.close();
 }
 await page.goto(`/api/documents/${invoice.id}/print/?business=${scenario.business}&language=fa`);await expect(page.locator('html')).toHaveAttribute('dir','rtl');await expect(page.locator('body')).toContainText(invoice.number);await page.screenshot({path:folder+'/screenshots/owner-print-dari.png',fullPage:true});
});
