import {test,expect} from '@playwright/test';
import {readFile,mkdir} from 'node:fs/promises';
let i18n:typeof import('../src/i18n').default;
let publicErrorMessage:typeof import('../src/error-display').publicErrorMessage;
let friendlyError:typeof import('../src/error-display').friendlyError;
let configureCalendar:typeof import('../src/calendar').configureCalendar;
let displayValue:typeof import('../src/calendar').displayValue;
test.beforeAll(async()=>{
 globalThis.localStorage={getItem:()=>null,setItem:()=>{},removeItem:()=>{},clear:()=>{},key:()=>null,length:0};
 i18n=(await import('../src/i18n')).default;await import('../src/localize');
 ({publicErrorMessage,friendlyError}=await import('../src/error-display'));
 ({configureCalendar,displayValue}=await import('../src/calendar'));
});

test('errors show translated primary copy without leaking diagnostic envelopes',async()=>{
 await i18n.changeLanguage('fa');
 const message='ارتفاع اصلی، سربلوک، کف و ضایعات باید برابر ارتفاع اندازه‌شده باشد.';
 const response={error:message,details:{},error_code:'validation_error',error_language:'fa',translation_complete:true,error_original:{error:'Main, top, bottom, and loss heights must reconcile to the measured source block.',details:{}}};
 expect(publicErrorMessage(response)).toBe(message);
 expect(publicErrorMessage({...response,translation_complete:false})).toBe(message);
 expect(publicErrorMessage({error:'Unhandled SQL detail',translation_complete:false,error_language:'fa'})).not.toContain('SQL');
 for(const value of [JSON.stringify(response),'error_code: validation_error · error_original: Main heights',new Error('[object Object]')]){
  expect(friendlyError(value)).not.toMatch(/error_code|error_original|validation_error|object Object/);
 }
 expect(publicErrorMessage(null,0)).toContain('اتصال');
 expect(publicErrorMessage({detail:'<html>Server traceback</html>'},500)).not.toContain('html');
 for(const language of ['ps','en']){await i18n.changeLanguage(language);expect(publicErrorMessage(null,0)).not.toContain('اتصال به سیستم');}
 await i18n.changeLanguage('fa');
});

test('confirmation value formatting follows calendar without modifying canonical dates',async()=>{
 await i18n.changeLanguage('fa');configureCalendar('jalali');
 expect(displayValue('2026-11-23')).toContain('۱۴۰۵');expect(displayValue('2026-11-23')).not.toContain('2026');
 expect(displayValue('دلیل نمونه')).toBe('دلیل نمونه');
 configureCalendar('gregorian');expect(displayValue('2026-11-23')).toContain('۲۰۲۶');
 configureCalendar('jalali');
});

test('real Dari return review, invalid trim, held block label and translated master names',async({page})=>{
 test.setTimeout(150000);
 test.skip(!process.env.ERP_UI_FIXES_FIXTURE,'Requires the private isolated UI-fixes fixture.');
 const fixture=JSON.parse(await readFile(process.env.ERP_UI_FIXES_FIXTURE!,'utf8'));
 const marker=await(await page.request.get('/verification-info/')).json();
 expect(marker.synthetic_only).toBe(true);expect(marker.database).toBe('verify_ui_fixes_20261123');
 await page.goto('/');await page.locator('[name=username]').fill(fixture.username);await page.locator('[name=password]').fill(fixture.password);await page.locator('[type=submit]').click();
 await expect(page.locator('.sidebar')).toBeVisible();await page.locator('.business-switch select').selectOption(String(fixture.business));
 await page.locator('.language-select').selectOption('fa');await page.waitForLoadState('networkidle');const solarSaved=page.waitForResponse(r=>r.url().endsWith('/api/preferences/')&&r.request().method()==='PATCH'&&r.request().postDataJSON().calendar==='jalali');await page.locator('.calendar-select').selectOption('jalali');await solarSaved;
 await page.goto('/production');await page.getByRole('button',{name:'برگشت مواد استفاده‌نشده',exact:true}).last().click();
 let form=page.locator('.modal').last();await expect(form.locator('[name=date_jalali]')).toBeVisible();
 let releaseConversion!:()=>void;const conversionGate=new Promise<void>(resolve=>{releaseConversion=resolve;});
 await page.route(/\/api\/calendar\/\?from=jalali/,async route=>{await conversionGate;await route.continue();});
 const conversion=page.waitForResponse(r=>r.url().includes('/api/calendar/?from=jalali'));
 await form.locator('[name=date_jalali]').fill('۱۴۰۵/۹/۲');
 await form.locator('[name=warehouse]').selectOption(String(fixture.floor));await form.locator('[name=destination]').selectOption(String(fixture.store));await form.locator('[name=product]').selectOption(String(fixture.raw));
 await form.locator('[name=quantity]').fill('1');await form.locator('[name=reason]').fill('برگشت آموزشی برای بررسی تاریخ');releaseConversion();await conversion;await page.waitForLoadState('networkidle');
 await expect(form.locator('[name=quantity]')).toHaveValue('1');await expect(form.locator('[name=reason]')).toHaveValue('برگشت آموزشی برای بررسی تاریخ');
 await page.unroute(/\/api\/calendar\/\?from=jalali/);await form.locator('[type=submit]').click();
 const review=page.locator('.review-action');await expect(review).toContainText('۱۴۰۵');await expect(review).not.toContainText(/20\d\d-\d\d-\d\d/);
 await mkdir('../.local/ui_fixes_20261123',{recursive:true});await page.screenshot({path:'../.local/ui_fixes_20261123/return-review-jalali.png'});
 await review.getByRole('button',{name:'انصراف',exact:true}).click();await form.getByRole('button',{name:'بستن',exact:true}).click();
 const calendarSaved=page.waitForResponse(r=>r.url().endsWith('/api/preferences/')&&r.request().method()==='PATCH'&&r.request().postDataJSON().calendar==='gregorian');
 await page.locator('.calendar-select').selectOption('gregorian');await calendarSaved;await page.getByRole('button',{name:'برگشت مواد استفاده‌نشده',exact:true}).last().click();form=page.locator('.modal').last();await expect(form.locator('input[type=date]').first()).toBeVisible();
 await form.locator('[name=warehouse]').selectOption(String(fixture.floor));await form.locator('[name=destination]').selectOption(String(fixture.store));await form.locator('[name=product]').selectOption(String(fixture.raw));await page.waitForLoadState('networkidle');await form.locator('[name=quantity]').fill('1');await form.locator('[name=reason]').fill('بررسی تقویم میلادی');await form.locator('[type=submit]').click();
 await expect(review).toContainText('۲۰۲۶');await review.getByRole('button',{name:'انصراف',exact:true}).click();await form.getByRole('button',{name:'بستن',exact:true}).click();await page.locator('.calendar-select').selectOption('jalali');
 await page.getByRole('button',{name:'اصلاح و سربلوک',exact:true}).last().click();form=page.locator('.modal').last();
 for(const [name,value]of Object.entries({block:String(fixture.ready_block),main_height_mm:'1000',top_height_mm:'40',bottom_height_mm:'40',loss_mm:'20',main_cost:'10000'})){
  const field=form.locator(`[name="${name}"]`);if(name==='block')await field.selectOption(value);else await field.fill(value);
 }
 const rejected=page.waitForResponse(r=>r.url().endsWith('/api/operations/trim/')&&r.request().method()==='POST');await form.locator('[type=submit]').click();expect((await rejected).status()).toBe(400);
 const error=page.locator('.error-notice');await expect(error).toContainText('ارتفاع');await expect(error).not.toContainText(/error_code|error_original|translation_complete|Main, top|details:/);
 await page.screenshot({path:'../.local/ui_fixes_20261123/trim-friendly-error.png'});await form.getByRole('button',{name:'بستن',exact:true}).click();
 await page.goto('/inventory');const held=page.locator('.block-card').filter({hasText:fixture.curing_code});await expect(held).toContainText('عمل‌آوری');await expect(held.locator('.block-saleability')).toContainText('۰');
 const label=await page.context().newPage();await label.goto(`/api/blocks/${fixture.curing_block}/label/?business=${fixture.business}`);await expect(label.locator('[data-field=remaining-height]')).toContainText('100 cm');await expect(label.locator('[data-field=available-height]')).toHaveText('0 cm');await expect(label.locator('[data-field=availability-reason]')).toContainText('عمل‌آوری');await label.screenshot({path:'../.local/ui_fixes_20261123/curing-label-explained.png',fullPage:true});await label.pdf({path:'../.local/ui_fixes_20261123/curing-label.pdf',preferCSSPageSize:true,printBackground:true});await label.close();
 await page.goto('/settings?section=setup');await page.locator('.setting-tabs').getByRole('button',{name:'انبارها',exact:true}).click();await page.locator('.access-toolbar>.button.primary').click();form=page.locator('.modal').last();
 await form.locator('[name=name_fa]').fill('گدام آزمایش');await form.locator('[name=name_en]').fill('Verification warehouse');await form.locator('[name=name_ps]').fill('د ازموینې ګودام');await form.locator('[name=location]').selectOption(String(fixture.location));await form.locator('[name=kind]').selectOption('store');
 await page.screenshot({path:'../.local/ui_fixes_20261123/warehouse-language-fields.png'});
 const created=page.waitForResponse(r=>r.url().endsWith('/api/catalog/warehouses/')&&r.request().method()==='POST');await form.locator('[type=submit]').click();expect((await created).status()).toBe(201);
 await page.locator('.language-select').selectOption('en');await expect(page.locator('html')).toHaveAttribute('dir','ltr');await expect(page.locator('.workspace')).toContainText('Verification warehouse');
 await page.locator('.language-select').selectOption('ps');await expect(page.locator('html')).toHaveAttribute('dir','rtl');await expect(page.locator('.workspace')).toContainText('د ازموینې ګودام');
});
