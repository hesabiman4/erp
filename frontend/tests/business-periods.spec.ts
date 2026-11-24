import {closeDocumentOrDialog} from './navigation';
import {test,expect} from '@playwright/test';
import {readFile,mkdir} from 'node:fs/promises';

test.setTimeout(180000);
test('prospective business calendar drives actual Jalali payroll and budget windows',async({page})=>{
 test.skip(process.env.ERP_DEMO_E2E!=='1','Synthetic payroll requires an explicitly enabled isolated QA database.');
 expect(process.env.ERP_E2E_BASE_URL).toContain(':5174');
 const secrets=JSON.parse(await readFile(process.env.ERP_E2E_CREDENTIALS||'../.local/verify_ui_20261029-credentials.json','utf8'));
 await page.goto('/');await page.locator('[name=username]').fill('owner');await page.locator('[name=password]').fill(secrets.owner);await page.locator('button[type=submit]').click();await expect(page.locator('.sidebar')).toBeVisible();
 await page.locator('.language-select').selectOption('fa');await page.locator('.calendar-select').selectOption('gregorian');await expect(page.locator('.calendar-select')).toHaveValue('gregorian');
 const originalBusiness=await page.locator('.business-switch select').inputValue();
 const created=await page.evaluate(async business=>{
  const csrf=decodeURIComponent(document.cookie.split('; ').find(s=>s.startsWith('csrftoken='))?.split('=')[1]||'');
  const response=await fetch('/api/businesses/',{method:'POST',headers:{'X-Business-ID':business,'X-CSRFToken':csrf,'Content-Type':'application/json'},body:JSON.stringify({name:'Synthetic calendar acceptance',slug:`calendar-qa-${Date.now()}`,manufacturing_mode:'actual',location_name:'Calendar test location',warehouse_name:'Calendar test warehouse'})});
  const data=await response.json();if(!response.ok)throw new Error(JSON.stringify(data));return data;
 },originalBusiness);
 await page.reload();await page.locator('.business-switch select').selectOption(String(created.id));await expect(page.locator('.business-switch select')).toHaveValue(String(created.id));
 const setup=await page.evaluate(async business=>{
  const csrf=decodeURIComponent(document.cookie.split('; ').find(s=>s.startsWith('csrftoken='))?.split('=')[1]||'');const headers={'X-Business-ID':String(business),'X-CSRFToken':csrf,'Content-Type':'application/json'};
  const c=await fetch('/api/catalog/',{headers});const catalog=await c.json();if(!c.ok)throw new Error(JSON.stringify(catalog));
  const e=await fetch('/api/catalog/employees/',{method:'POST',headers,body:JSON.stringify({name:'Jalali payroll acceptance',code:'CALENDAR-001',location:catalog.locations[0].id,kind:'monthly',rate:'31000',join_date:'2027-03-21',effective_date:'2027-03-21',active:true})});const employee=await e.json();if(!e.ok)throw new Error(JSON.stringify(employee));
  return {employee,location:catalog.locations[0].id,salary:catalog.accounts.find((a:any)=>a.code==='SALARY').id};
 },created.id);
 await page.goto('/operations?view=business_periods');await expect(page.locator('.growth-content')).toContainText('تقویم کاری و دوره‌های واقعی');
 const policyForm=page.locator('form').filter({has:page.locator('[name=calendar_reason]')});await policyForm.locator('[name=policy_calendar]').selectOption('jalali');await policyForm.locator('[name=effective_from]').fill('2027-03-21');await policyForm.locator('[name=calendar_reason]').fill('Synthetic reviewed contractual transition for browser acceptance');
 const policyResponse=page.waitForResponse(r=>r.url().endsWith('/api/operations/calendar_policy/')&&r.request().method()==='POST');await policyForm.locator('button[type=submit]').click();const policy=await policyResponse;expect(policy.status(),await policy.text()).toBe(201);await expect(page.locator('.growth-content tbody')).toContainText('Synthetic reviewed contractual transition');
 await page.goto('/employees');await page.locator('.section-head button').filter({hasText:'ثبت معاش'}).click();let dialog=page.locator('.modal');await dialog.locator('[name=employee]').selectOption(String(setup.employee.id));await dialog.locator('[name=date]').fill('2027-04-20');await dialog.locator('[name=period_calendar]').selectOption('jalali');await dialog.locator('[name=business_month]').selectOption('1406-01');await expect(dialog.locator('[data-period-boundaries]')).toContainText(/۲۰۲۷|2027/);
 const payrollResponse=page.waitForResponse(r=>r.url().endsWith('/api/operations/payroll_accrue/')&&r.request().method()==='POST');await dialog.locator('button[type=submit]').click();const salary=await payrollResponse;const salaryData=await salary.json();expect(salary.status(),JSON.stringify(salaryData)).toBe(201);expect(salaryData.document.amount).toBe('31000.00');expect(salaryData.document.result.period_key).toBe('jalali:1406-01');expect(salaryData.document.result.earning_from).toBe('2027-03-21');expect(salaryData.document.result.earning_through).toBe('2027-04-20');await closeDocumentOrDialog(page);
 await page.goto('/operations?view=budgets_actual');await page.locator('.section-head button.primary').click();dialog=page.locator('.modal');await dialog.locator('[name=period_calendar]').selectOption('jalali');await dialog.locator('[name=business_month]').selectOption('1406-01');await dialog.locator('[name=account]').selectOption(String(setup.salary));await dialog.locator('[name=location]').selectOption(String(setup.location));await dialog.locator('[name=line]').selectOption('shared');await dialog.locator('[name=amount]').fill('35000');
 const budgetResponse=page.waitForResponse(r=>r.url().endsWith('/api/operations/budget_set/')&&r.request().method()==='POST');await dialog.locator('button[type=submit]').click();const budget=await budgetResponse;expect(budget.status(),await budget.text()).toBe(201);await closeDocumentOrDialog(page);
 await page.locator('[name=budget_filter_calendar]').selectOption('jalali');await page.locator('.growth-filter [name=business_month]').selectOption('1406-01');await expect(page.locator('.growth-content tbody')).toContainText('۳۱٬۰۰۰');await expect(page.locator('.growth-content tbody')).toContainText('۳۵٬۰۰۰');
 const evidence=process.env.ERP_E2E_OUTPUT||'../.local/design/business-periods';await mkdir(evidence,{recursive:true});await page.screenshot({path:`${evidence}/jalali-budget-actual.png`,fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.goto('/operations?view=business_periods');await expect(page.locator('.growth-content')).toContainText('تقویم کاری');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 await page.setViewportSize({width:1440,height:1000});await page.locator('.business-switch select').selectOption(originalBusiness);await page.locator('.calendar-select').selectOption('jalali');
});
