import {closeDocumentOrDialog} from './navigation';
import {test,expect} from '@playwright/test';
import {readFile,mkdir} from 'node:fs/promises';
const evidence=process.env.ERP_E2E_OUTPUT||'../.local/design/calendar-statements';
test.setTimeout(180000);
test.beforeEach(async({page})=>{
 test.skip(process.env.ERP_DEMO_E2E!=='1','Only the isolated QA database is authorized for synthetic workflows.');
 expect(process.env.ERP_E2E_BASE_URL).toContain(':5174');
 const credentials=JSON.parse(await readFile(process.env.ERP_E2E_CREDENTIALS||'../.local/verify_ui_20261029-credentials.json','utf8'));
 await page.goto('/');await page.locator('[name=username]').fill('owner');await page.locator('[name=password]').fill(credentials.owner);await page.locator('[type=submit]').click();await expect(page.locator('.sidebar')).toBeVisible();await page.locator('.calendar-select').selectOption('jalali');await expect(page.locator('.calendar-select')).toHaveValue('jalali');await mkdir(evidence,{recursive:true});
});

test('Jalali popup, shared dates, validation, persistence and mobile calendar',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('/customers');await expect(page.locator('.party-profile')).toBeVisible();await expect(page.locator('input[type=date]')).toHaveCount(0);
 const trigger=page.locator('.center-asof .calendar-trigger');await trigger.click();let calendar=page.getByRole('dialog',{name:'تقویم هجری شمسی',exact:true});await expect(calendar).toBeVisible();await expect(calendar.getByRole('gridcell')).toHaveCount(42);await calendar.getByLabel('سال شمسی',{exact:true}).selectOption('1405');await calendar.getByLabel('ماه شمسی',{exact:true}).selectOption('8');await expect(calendar.getByRole('grid',{name:'عقرب ۱۴۰۵',exact:true})).toBeVisible();
 await page.screenshot({path:`${evidence}/jalali-desktop.png`});
 await calendar.getByRole('gridcell',{name:'1405-08-07',exact:true}).click();await expect(page.locator('.center-asof input[type=text]')).toHaveValue('۱۴۰۵/۰۸/۰۷');await expect(page.locator('.party-profile')).toBeVisible();
 await page.goto('/accounting?report=balance_sheet');await expect(page.locator('.financial-statement')).toBeVisible();await expect(page.locator('input[type=date]')).toHaveCount(0);await page.locator('.report-dates .calendar-trigger').first().click();await expect(page.getByRole('dialog',{name:'تقویم هجری شمسی'})).toBeVisible();await closeDocumentOrDialog(page);
 await page.goto('/operations?view=equipment');await page.locator('.section-head button.primary').click();const modal=page.locator('.modal');await modal.locator('[name=date_jalali]').fill('۱۴۰۵/۱۲/۳۰');await modal.locator('[name=date_jalali]').blur();await expect(modal.getByRole('alert')).toBeVisible();await modal.locator('.calendar-trigger').first().click();await expect(page.getByRole('dialog',{name:'تقویم هجری شمسی'})).toBeVisible();await closeDocumentOrDialog(page);await expect(modal).toBeVisible();await modal.locator('[name=date_jalali]').fill('۱۴۰۵/۰۱/۰۱');await modal.locator('[name=date_jalali]').blur();await expect(modal.locator('[name=date]')).toHaveValue('2026-03-21');await closeDocumentOrDialog(page);
 await page.reload();await expect(page.locator('.calendar-select')).toHaveValue('jalali');await page.locator('.calendar-select').selectOption('gregorian');await page.goto('/suppliers');await expect(page.locator('input[type=date]').first()).toBeVisible();await expect(page.locator('.calendar-trigger')).toHaveCount(0);await page.locator('.calendar-select').selectOption('jalali');await expect(page.locator('input[type=date]')).toHaveCount(0);
 await page.setViewportSize({width:390,height:844});await page.locator('.center-asof .calendar-trigger').click();calendar=page.getByRole('dialog',{name:'تقویم هجری شمسی'});await expect(calendar).toBeInViewport();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:`${evidence}/jalali-mobile.png`,fullPage:true});expect(errors).toEqual([]);
});

test('employee opens a real statement page with separate salary and advance ledgers',async({page})=>{
 const business=await page.locator('.business-switch select').inputValue();
 const data=await page.evaluate(async business=>{
  const csrf=decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.split('=')[1]||'');const headers={'X-Business-ID':business,'X-CSRFToken':csrf,'Content-Type':'application/json'};
  const get=async(path:string)=>{const r=await fetch(path,{headers});if(!r.ok)throw new Error(`GET ${path}: ${r.status}`);return r.json();};
  const post=async(path:string,payload:unknown)=>{const r=await fetch(path,{method:'POST',headers:{...headers,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(payload)});const body=await r.json();if(!r.ok)throw new Error(`${path}: ${r.status} ${JSON.stringify(body)}`);return body;};
  const catalog=await get('/api/catalog/');const location=catalog.locations[0].id;const stamp=Date.now();
  const employee=await post('/api/catalog/employees/',{code:`ST-${stamp}`,name:`Statement employee ${stamp}`,kind:'monthly',rate:'10000',location,join_date:'2026-09-01',effective_date:'2026-09-01',advance_limit:'5000',active:true});
  const op=async(action:string,payload:object)=>post(`/api/operations/${action}/`,payload);
  await op('opening_cash',{date:'2026-09-01',location,amount:'10000',reason:'Synthetic QA opening for employee statement'});
  await op('employee_advance',{date:'2026-09-03',employee:employee.id,amount:'3500',account:'CASH'});
  const payroll=await op('payroll_accrue',{date:'2026-09-30',employee:employee.id,period:'2026-09'});
  await op('payroll_settle',{date:'2026-10-01',payroll:payroll.document.id,amount:'6000',advance_recovery:'2000',cash_account:'CASH'});
  return{employee,payroll};
 },business);
 await page.goto('/employees');await page.getByRole('textbox',{name:'جستجوی کارمند',exact:true}).fill(data.employee.name);await page.locator('.panel tbody tr').filter({hasText:data.employee.name}).click();await expect(page).toHaveURL(new RegExp(`/employees/${data.employee.id}$`));await expect(page.locator('.modal')).toHaveCount(0);await expect(page.locator('.employee-metrics')).toBeVisible();
 const metric=(label:string)=>page.locator('.employee-metric').filter({hasText:label}).locator('strong');await expect(metric('معاش ناخالص ثبت‌شده')).toContainText('۱۰٬۰۰۰');await expect(metric('معاش پرداخت‌شده نقدی')).toContainText('۶٬۰۰۰');await expect(metric('معاش قابل‌پرداخت')).toContainText('۲٬۰۰۰');await expect(metric('پیش‌معاش باقی‌مانده')).toContainText('۱٬۵۰۰');await expect(page.locator('.employee-statement-page tbody tr')).toHaveCount(2);
 await page.screenshot({path:`${evidence}/employee-salary-statement.png`,fullPage:true});await page.locator('.employee-statement-page tbody tr').first().click();await expect(page.locator('.document-detail-page')).toContainText(data.payroll.document.number);await expect(page.locator('.document-view')).toContainText(data.employee.name);await closeDocumentOrDialog(page);
 await page.getByRole('tab',{name:'گردش پیش‌معاش',exact:true}).click();await expect(page.locator('.employee-ledger-closing strong')).toContainText('۱٬۵۰۰');await page.screenshot({path:`${evidence}/employee-advance-statement.png`,fullPage:true});await page.reload();await expect(page.locator('.employee-statement-page')).toContainText(data.employee.name);
 await page.emulateMedia({media:'print'});await page.pdf({path:`${evidence}/employee-statement.pdf`,format:'A4',printBackground:true});await page.emulateMedia({media:'screen'});await page.setViewportSize({width:390,height:844});await expect(page.locator('.sidebar')).not.toBeInViewport();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:`${evidence}/employee-statement-mobile.png`,fullPage:true});
});

test('chart of accounts provides practical classifications and the complete manual',async({page})=>{
 await page.goto('/accounting?report=chart_of_accounts');await expect(page.locator('.account-browser')).toBeVisible();await expect(page.locator('.account-browser tbody tr')).toHaveCount(65);await page.getByLabel('جستجوی حساب',{exact:true}).fill('PAYROLL');await expect(page.locator('.account-browser tbody tr')).toHaveCount(2);await page.getByLabel('جستجوی حساب',{exact:true}).fill('RAW');await page.locator('.account-browser tbody tr').filter({hasText:'RAW'}).first().click();await expect(page.locator('.account-insight')).toContainText('سند دستی مجاز نیست');
 await page.getByLabel('جستجوی حساب',{exact:true}).fill('');await page.getByLabel('نوع حساب',{exact:true}).selectOption('asset');await page.screenshot({path:`${evidence}/chart-of-accounts-guidance.png`,fullPage:true});const business=await page.locator('.business-switch select').inputValue();const response=await page.request.get(`/api/accounting-guide/?business=${business}`);expect(response.status()).toBe(200);expect(response.headers()['content-type']).toContain('application/pdf');expect(response.headers()['content-language']).toBe('fa-AF');expect((await response.body()).subarray(0,5).toString()).toBe('%PDF-');
 await page.locator('.language-select').selectOption('en');await expect(page.getByRole('link',{name:'Download the complete account manual · PDF'})).toHaveAttribute('href',/language=en/);
});

