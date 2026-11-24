import {closeDocumentOrDialog} from './navigation';
import {test,expect} from '@playwright/test';
import {readFile,mkdir} from 'node:fs/promises';
const evidence=process.env.ERP_E2E_OUTPUT||'../.local/design/accounting-e2e';
test.setTimeout(120000);
test.beforeEach(async({page})=>{
 const credentials=JSON.parse(await readFile(process.env.ERP_E2E_CREDENTIALS||'../.local/demo-credentials.json','utf8'));
 await page.goto('/');await page.locator('[name=username]').fill('owner');await page.locator('[name=password]').fill(credentials.owner);
 const login=page.waitForResponse(r=>r.url().endsWith('/api/session/')&&r.request().method()==='POST');await page.locator('[type=submit]').click();expect((await login).status()).toBe(200);await expect(page.locator('.accounting-home')).toBeVisible({timeout:60000});
 await expect(page.locator('.loading')).toHaveCount(0,{timeout:60000});await mkdir(evidence,{recursive:true});
});

test('accounting periods, create menu and customer/supplier statements',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.getByRole('button',{name:'امروز',exact:true}).click();await expect(page.locator('.loading')).toHaveCount(0);
 await page.getByRole('button',{name:'از آغاز',exact:true}).click();await expect(page.locator('.loading')).toHaveCount(0);
 await page.locator('.quick-create>button').click();await expect(page.locator('#global-create-panel')).toBeVisible();
 await page.locator('.create-menu button').filter({hasText:'ثبت بل تأمین‌کننده'}).click();
 await expect(page.getByRole('dialog')).toBeVisible();await expect(page.locator('.quick-create>button')).toHaveAttribute('aria-expanded','false');await closeDocumentOrDialog(page);
 await page.locator('.sidebar a[href="/customers"]').click();await expect(page.locator('.party-profile')).toBeVisible();
 const business=await page.locator('.business-switch select').inputValue();
 const expected=await page.evaluate(async business=>{const r=await fetch('/api/reports/customer_balances/',{headers:{'X-Business-ID':business}});return r.json()},business);
 await expect(page.locator('.directory-list>button')).toHaveCount(expected.rows.length);
 await expect(page.locator('.center-money-bar>button').first().locator('strong')).not.toHaveText('—');
 const firstName=await page.locator('.party-profile h2').innerText();
 await page.locator('.directory-search input').fill(firstName);await expect(page.locator('.directory-list>button').first()).toContainText(firstName);
 await page.locator('.directory-search input').fill('no-matching-party-XYZ');await expect(page.locator('.directory-list>button')).toHaveCount(0);
 await expect(page.locator('.party-profile')).toHaveCount(0);await page.locator('.directory-search input').fill('');
 await page.getByRole('tab',{name:'صورت‌حساب',exact:true}).click();await expect(page.locator('.statement-closing')).toBeVisible();
 await page.screenshot({path:`${evidence}/accounting-customers.png`});
 await page.emulateMedia({media:'print'});await page.pdf({path:`${evidence}/customer-statement.pdf`,format:'A4',printBackground:true});await page.emulateMedia({media:'screen'});
 await page.getByRole('tab',{name:'مشخصات و یادداشت',exact:true}).click();await expect(page.locator('.party-contact-details')).toBeVisible();
 await page.locator('.sidebar a[href="/suppliers"]').click();await expect(page.locator('.party-profile')).toBeVisible();
 await expect(page.locator('.section-head h1')).toHaveText('مرکز تأمین‌کنندگان');await page.screenshot({path:`${evidence}/accounting-suppliers.png`});
 await page.setViewportSize({width:390,height:844});await expect(page.locator('.location-select')).toBeVisible();await expect(page.locator('.loading')).toHaveCount(0);await expect(page.locator('.sidebar')).not.toBeInViewport();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:`${evidence}/accounting-mobile-center.png`,fullPage:true});
 await page.locator('.language-select').selectOption('en');await expect(page.locator('html')).toHaveAttribute('dir','ltr');
 await expect(page.locator('.section-head h1')).toHaveText('Supplier center');expect(await page.locator('.center-money-bar strong').first().innerText()).not.toMatch(/[۰-۹]/);
 await page.setViewportSize({width:1440,height:1000});await page.screenshot({path:`${evidence}/accounting-english-center.png`});
 expect(errors).toEqual([]);
});

test('customer created and edited from the center persists in the database',async({page})=>{
 test.skip(process.env.ERP_DEMO_E2E!=='1','Synthetic writes require ERP_DEMO_E2E=1 and an isolated test database.');
 const name=`Center test ${Date.now()}`;await page.goto('/customers');await expect(page.locator('.party-profile')).toBeVisible();
 await page.getByRole('button',{name:'مشتری جدید',exact:true}).click();await page.locator('[name=name]').fill(name);await page.locator('[name=phone]').fill('0700000123');await page.locator('[name=address]').fill('هرات - آزمایشی');
 const save=page.waitForResponse(r=>r.url().endsWith('/api/catalog/parties/')&&r.request().method()==='POST');await page.locator('[role=dialog] [type=submit]').click();expect((await save).status()).toBe(201);
 await page.locator('.directory-search input').fill(name);await page.locator('.directory-list>button').first().click();await expect(page.locator('.party-profile h2')).toHaveText(name);
 await page.getByRole('button',{name:'ویرایش مشخصات',exact:true}).click();await page.locator('[name=notes]').fill('Customer center persistence check');await page.locator('[role=dialog] [type=submit]').click();await expect(page.getByRole('dialog')).toHaveCount(0);
 await page.reload();await page.locator('.directory-search input').fill(name);await page.locator('.directory-list>button').first().click();await page.getByRole('tab',{name:'مشخصات و یادداشت',exact:true}).click();await expect(page.locator('.party-contact-details')).toContainText('Customer center persistence check');
});

test('open customer and supplier balances can be paid directly from their centers',async({page})=>{
 test.skip(process.env.ERP_DEMO_E2E!=='1','Synthetic transactions require an isolated database.');
 const business=await page.locator('.business-switch select').inputValue();
 const arranged=await page.evaluate(async business=>{
  const headers={'X-Business-ID':business,'Content-Type':'application/json','X-CSRFToken':decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))!.split('=').slice(1).join('='))};
  const post=async(path:string,payload:any)=>{const r=await fetch(path,{method:'POST',headers:{...headers,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(payload)});if(!r.ok)throw new Error(await r.text());return r.json()};
  const catalog=await (await fetch('/api/catalog/',{headers})).json();const location=catalog.locations.find((r:any)=>r.code==='HERAT').id;
  const date=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kabul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const stamp=Date.now();const customer=await post('/api/catalog/parties/',{name:`Center AR ${stamp}`,kind:'customer',phone:'0700000321'});const supplier=await post('/api/catalog/parties/',{name:`Center AP ${stamp}`,kind:'supplier',phone:'0700000322'});
  const ar=await post('/api/operations/opening_receivable/',{date,location,party:customer.id,amount:'750',reason:'Synthetic center payment test'});
  const ap=await post('/api/operations/opening_payable/',{date,location,party:supplier.id,amount:'950',reason:'Synthetic center payment test'});
  return {customer,supplier,ar:ar.document,ap:ap.document};
 },business);
 for(const item of [{route:'/customers',party:arranged.customer,invoice:arranged.ar,action:'receipt',amount:'750'},{route:'/suppliers',party:arranged.supplier,invoice:arranged.ap,action:'supplier_payment',amount:'950'}]){
  await page.goto(item.route);await expect(page.locator('.directory-search input')).toBeVisible();await page.locator('.directory-search input').fill(item.party.name);await page.locator('.directory-list>button').first().click();
  await expect(page.locator('.party-profile h2')).toHaveText(item.party.name);await page.getByRole('tab',{name:'بل‌های باز',exact:true}).click();
  await page.locator('.party-detail tbody tr').filter({hasText:item.invoice.number}).getByRole('button').click();await expect(page.locator('[name=invoice]')).toHaveValue(String(item.invoice.id));await expect(page.locator('[name=amount]')).toHaveValue(item.amount+'.00');
  const locations=await page.locator('[name=location] option').allTextContents();expect(locations.length).toBeGreaterThan(1);
  await page.locator('[name=location]').selectOption({label:'دفتر مرکزی هرات'});await page.locator('[name=cash_account]').selectOption('CASH');
  const saved=page.waitForResponse(r=>r.url().endsWith(`/api/operations/${item.action}/`)&&r.request().method()==='POST');await page.locator('[role=dialog] button[type=submit]').click();expect((await saved).status()).toBe(201);
  await expect(page.locator('.document-detail-page')).toBeVisible();await closeDocumentOrDialog(page);await expect(page.locator('.party-detail tbody tr')).toHaveCount(0);await expect(page.locator('.party-profile-totals>div').first().locator('strong')).toContainText('۰');
 }
});
