import {test,expect} from '@playwright/test';
import {readFile,mkdir} from 'node:fs/promises';

test.setTimeout(120000);
test('release diagnostics reads current metadata and preserves database isolation without operator mutations',async({page})=>{
 test.skip(process.env.ERP_DEMO_E2E!=='1','Requires an explicitly selected isolated QA application.');
 expect(process.env.ERP_E2E_BASE_URL).toContain(':5174');
 const credentials=JSON.parse(await readFile(process.env.ERP_E2E_CREDENTIALS||'../.local/verify_ui_20261029-credentials.json','utf8'));
 const errors:string[]=[];const writes:string[]=[];
 page.on('pageerror',error=>errors.push(error.message));
 page.on('request',request=>{if(request.method()!=='GET'&&/\/api\/(?:operations|documents|runtime-management|business)\//.test(request.url()))writes.push(request.url());});
 await page.goto('/');await page.locator('[name=username]').fill('owner');await page.locator('[name=password]').fill(credentials.owner);await page.locator('[type=submit]').click();await expect(page.locator('.sidebar')).toBeVisible();
 await page.locator('.language-select').selectOption('en');await expect(page.locator('.language-select')).toHaveValue('en');
 await page.goto('/operations?view=runtime_management');
 await expect(page.locator('.runtime-management')).toContainText('Release, installation and recovery');
 await expect(page.locator('.runtime-release-cards')).toContainText('Database');
 await expect(page.locator('.runtime-management')).toContainText('No matching evidence');
 await expect(page.locator('.runtime-management')).toContainText('Destination configuration is deferred');
 await page.getByRole('button',{name:'Refresh checks',exact:true}).click();
 const report=await page.evaluate(async()=>{const business=(document.querySelector('.business-switch select') as HTMLSelectElement).value;const response=await fetch('/api/runtime-management/',{headers:{'X-Business-ID':business}});return {status:response.status,cache:response.headers.get('Cache-Control'),data:await response.json()};});
 expect(report.status).toBe(200);expect(report.cache).toContain('no-store');expect(report.data.actions_available_over_http).toBe(false);expect(report.data.database.engine).toBe('postgresql');
 const serialized=JSON.stringify(report.data);expect(serialized).not.toContain('PGPASSWORD');expect(serialized).not.toContain('.env.local');expect(serialized).not.toContain('C:\\Users\\');expect(writes).toEqual([]);
 await mkdir('../.local/design/runtime-management-browser',{recursive:true});await page.screenshot({path:'../.local/design/runtime-management-browser/desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});await expect(page.locator('.sidebar')).not.toBeInViewport();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 await page.screenshot({path:'../.local/design/runtime-management-browser/phone.png',fullPage:true});expect(errors).toEqual([]);
});
