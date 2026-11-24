import {test,expect} from '@playwright/test';
import {readFile,mkdir} from 'node:fs/promises';
import {taxDate,taxNumber,taxError} from '../src/tax-display';

test('tax presentation preserves decimal strings, Eastern digits and explicit calendar boundaries',()=>{
 expect(taxNumber('9999999999999999.123456','fa')).toBe('۹٬۹۹۹٬۹۹۹٬۹۹۹٬۹۹۹٬۹۹۹٫۱۲۳۴۵۶');
 expect(taxNumber('1000.00','ps')).toBe('۱٬۰۰۰');expect(taxNumber('12.123456','en')).toBe('12.123456');
 expect(taxNumber('1.0000005','en',6)).toBe('1.000001');expect(taxNumber(null,'fa')).toBe('—');
 const months=['حمل','ثور','جوزا','سرطان','اسد','سنبله','میزان','عقرب','قوس','جدی','دلو','حوت'];
 expect(taxDate('2026-07-11','fa','jalali',months)).toBe('۲۰ سرطان ۱۴۰۵');
 expect(taxDate('2026-07-10T21:00:00Z','fa','jalali',months)).toBe('۲۰ سرطان ۱۴۰۵ · ۰۱:۳۰');
 expect(taxDate('2026-07-11','ps','gregorian',months)).toBe('۲۰۲۶/۰۷/۱۱');
 expect(taxDate('invalid','en','jalali',months)).toBe('—');
 const original={detail:{error:'پیام دری',translation_complete:true,error_original:{error:'Original English evidence'}}};
 const visible=taxError(original) as Error;expect(visible.message).toBe('پیام دری');expect(visible.cause).toBe(original);
});

test('synthetic tax review: structured Dari forms, exact preview, history, revision and tenant isolation',async({page,browser})=>{
 test.setTimeout(180000);
 test.skip(process.env.ERP_TAX_ACCEPTANCE!=='1','Only the explicit isolated tax verification database.');
 expect(process.env.ERP_E2E_BASE_URL).toBe('http://localhost:8082');
 const marker=await(await page.request.get('/pilot-info/')).json();expect(marker.pilot_id).toBe('tax_schedule_verification');expect(marker.synthetic_only).toBe(true);
 const fixture=JSON.parse(await readFile('../.local/audit_20261122/tax-browser-credentials.json','utf8'));
 expect(fixture.database).toBe('verify_upgrade_tax_20261122');
 const auth=fixture.credentials.tax_owner;await page.goto('/');await page.locator('[name=username]').fill(auth.username);await page.locator('[name=password]').fill(auth.password);await page.locator('[type=submit]').click();
 await expect(page.locator('.business-switch')).toBeVisible();await page.locator('.business-switch select').selectOption(String(fixture.business));
 await page.locator('.language-select').selectOption('fa');await page.locator('.calendar-select').selectOption('jalali');await page.goto('/settings?section=tax');
 await expect(page.getByRole('heading',{name:'نسخه‌های مالیه افغانستان',exact:true})).toBeVisible();await expect(page.locator('html')).toHaveAttribute('dir','rtl');
 const version='QA-'+Date.now();
 await page.getByRole('button',{name:'نسخهٔ مالیاتی تازه',exact:true}).first().click();const form=page.locator('.tax-schedule-form');await expect(form.locator('[name=tax-name_fa]')).toBeFocused();
 await form.locator('[name=tax-name_fa]').fill('قاعدهٔ آزمایشی مالیه معاش');await form.locator('[name=tax-name_en]').fill('Synthetic salary schedule');await form.locator('[name=tax-name_ps]').fill('د معاش ازمایښتي مالیاتي نسخه');
 await form.locator('[name=tax-schedule_version]').fill(version);
 const convert=page.waitForResponse(r=>r.url().includes('/api/calendar/?from=jalali')&&r.request().method()==='GET');
 await form.locator('[name=tax-effective_from_jalali]').fill('۱۴۰۵/۰۴/۲۰');await form.locator('[name=tax-effective_from_jalali]').press('Tab');await convert;
 await form.locator('[name=tax-source_url]').fill('https://example.com/synthetic-tax-review');await form.locator('[name=tax-notes]').fill('آزمایش نرم‌افزار؛ قاعدهٔ واقعی این تجارت نیست.');
 for(const row of [{lower:'10000',rate:'10',fixed:'0'},{lower:'100000',rate:'15',fixed:'9000'}]){
  await form.getByRole('button',{name:'افزودن طبقه',exact:true}).click();const bracket=form.locator('.tax-bracket-row').last();for(const [key,value] of Object.entries(row))await bracket.locator(`[name$=-${key}]`).fill(value);
 }
 await form.locator('[name=tax-create-reason]').fill('آزمایش ثبت و بررسی؛ بدون تأیید مالیاتی واقعی.');
 await form.locator('[name=tax-bracket-0-rate]').fill('101');const rejectedResponse=page.waitForResponse(r=>r.url().endsWith('/api/tax-schedules/')&&r.request().method()==='POST');await form.getByRole('button',{name:'ذخیرهٔ نسخه برای بررسی',exact:true}).click();expect((await rejectedResponse).status()).toBe(400);
 await expect(page.locator('.error-notice')).toContainText('نسخهٔ مالیاتی');await expect(page.locator('.error-notice')).not.toContainText('Review the tax');await form.locator('[name=tax-bracket-0-rate]').fill('0');
 const createdResponse=page.waitForResponse(r=>r.url().endsWith('/api/tax-schedules/')&&r.request().method()==='POST');await form.getByRole('button',{name:'ذخیرهٔ نسخه برای بررسی',exact:true}).click();const created=await createdResponse;expect(created.status(),await created.text()).toBe(201);const rule=(await created.json()).rule;
 expect(rule.requires_confirmation).toBe(true);expect(rule.effective_from).toBe('2026-07-11');expect(rule.brackets).toHaveLength(3);
 const detail=page.locator('.tax-schedule-detail');await expect(detail).toContainText(version);await expect(page.locator('.tax-schedule-warning')).toBeVisible();
 await detail.locator('[name=tax-preview-base]').fill('۲۰۰۰۰');await detail.getByRole('button',{name:'محاسبهٔ آزمایشی',exact:true}).click();await expect(detail.locator('.tax-preview [role=status]')).toContainText('۱٬۰۰۰');await expect(detail.locator('.tax-preview [role=status]')).toContainText('تأییدنشده');
 const url=`/api/tax-schedules/${rule.id}/`;
 for(const [action,label,revision] of [['confirm','تأیید نسخهٔ مالیاتی',1],['revoke','لغو تأیید نسخهٔ مالیاتی',2]] as const){
  await detail.locator('[name=tax-confirm-reason]').fill('فقط بررسی آزمایشی سابقهٔ تصمیم در دیتابیس جداگانه.');await detail.getByRole('button',{name:label,exact:true}).click();
  const response=page.waitForResponse(r=>r.url().endsWith(url)&&r.request().method()==='POST'&&r.request().postDataJSON().action===action);await page.locator('.review-action').getByRole('button',{name:'تأیید و ادامه',exact:true}).click();const result=await response;expect(result.status(),await result.text()).toBe(200);expect((await result.json()).rule.confirmation_revision).toBe(revision);
  await expect(detail.locator('.tax-schedule-history>li')).toHaveCount(revision+1);
 }
 await detail.getByRole('button',{name:'ایجاد نسخهٔ اصلاحی',exact:true}).click();await form.locator('[name=tax-schedule_version]').fill(version+'-REV2');await form.locator('[name=tax-name_fa]').fill('نسخهٔ اصلاحی آزمایش');await form.locator('[name=tax-create-reason]').fill('اصلاح نام آزمایشی؛ نسخهٔ اول باید محفوظ بماند.');
 const revisionResponse=page.waitForResponse(r=>r.url().endsWith('/api/tax-schedules/')&&r.request().method()==='POST');await form.getByRole('button',{name:'ذخیرهٔ نسخه برای بررسی',exact:true}).click();const revision=(await(await revisionResponse).json()).rule;expect(revision.supersedes).toBe(rule.id);expect(revision.requires_confirmation).toBe(true);
 await expect(detail).toContainText(version+'-REV2');await mkdir('../.local/audit_20261122',{recursive:true});await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'../.local/audit_20261122/tax-dari-detail.png',fullPage:true});
 await page.locator('.language-select').selectOption('en');await expect(page.getByRole('heading',{name:'Afghanistan tax schedules',exact:true})).toBeVisible();await expect(page.locator('html')).toHaveAttribute('dir','ltr');await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'../.local/audit_20261122/tax-english-detail.png',fullPage:true});
 await page.locator('.language-select').selectOption('ps');await expect(page.getByRole('heading',{name:'د افغانستان مالیاتي نسخې',exact:true})).toBeVisible();await expect(page.locator('html')).toHaveAttribute('dir','rtl');await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'../.local/audit_20261122/tax-pashto-detail.png',fullPage:true});
 await page.locator('.business-switch select').selectOption(String(fixture.other));await expect(detail).toHaveCount(0);await expect(page.locator('.tax-schedule-warning')).toHaveCount(0);
 const forbidden=await page.request.get(url,{headers:{'X-Business-ID':String(fixture.other),'Accept-Language':'fa-AF'}});expect(forbidden.status()).toBe(400);expect((await forbidden.json()).translation_complete).toBe(true);
 const original=await(await page.request.get(url,{headers:{'X-Business-ID':String(fixture.business)}})).json();expect(original.rule.name_fa).toBe('قاعدهٔ آزمایشی مالیه معاش');expect(original.history_total).toBe(3);
 const context=await browser.newContext();const viewer=await context.newPage();await viewer.goto('/');await viewer.locator('[name=username]').fill(fixture.credentials.tax_viewer.username);await viewer.locator('[name=password]').fill(fixture.credentials.tax_viewer.password);await viewer.locator('[type=submit]').click();await expect(viewer.locator('.sidebar')).toBeVisible();await viewer.goto('/settings?section=tax');await expect(viewer.getByRole('heading',{name:'نسخه‌های مالیه افغانستان',exact:true})).toBeVisible();await expect(viewer.getByRole('button',{name:'نسخهٔ مالیاتی تازه',exact:true})).toHaveCount(0);
 const noConfirm=await viewer.request.post(url,{headers:{'X-Business-ID':String(fixture.business)},data:{action:'confirm',reason:'Viewer cannot approve this synthetic revision.',expected_revision:2}});expect(noConfirm.status()).toBe(403);await context.close();
});
