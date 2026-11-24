import {test,expect} from '@playwright/test';
import {readFile,writeFile} from 'node:fs/promises';

test.setTimeout(180000);
test('built document navigation works with measured latency and constrained bandwidth without posting',async({page,context})=>{
 test.skip(process.env.ERP_SLOW_RUNTIME_E2E!=='1','Read-only built-runtime network acceptance must be explicitly enabled.');
 const base=process.env.ERP_RUNTIME_URL||'http://127.0.0.1:8080';const credentials=JSON.parse(await readFile(process.env.ERP_RUNTIME_CREDENTIALS||'../.local/demo-credentials.json','utf8'));
 const errors:string[]=[];const mutations:string[]=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()!=='GET'&&/\/api\/(operations|documents)\//.test(r.url()))mutations.push(r.url());});
 await page.goto(base+'/');await page.locator('[name=username]').fill('owner');await page.locator('[name=password]').fill(credentials.owner);await page.locator('[type=submit]').click();await expect(page.locator('.sidebar')).toBeVisible();
 const cdp=await context.newCDPSession(page);await cdp.send('Network.enable');await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:200,downloadThroughput:384000,uploadThroughput:192000});
 const started=Date.now();await page.goto(base+'/sales');const row=page.locator('.interactive-table tbody tr').first();await expect(row).toBeVisible({timeout:120000});await row.click();await expect(page.locator('.document-detail-page')).toBeVisible({timeout:120000});await expect(page.locator('.modal')).toHaveCount(0);await page.reload();await expect(page.locator('.document-detail-page')).toBeVisible({timeout:120000});await page.goBack();await expect(page.locator('.data-grid-search input')).toBeVisible({timeout:120000});
 expect(mutations).toEqual([]);expect(errors).toEqual([]);
 await writeFile('../.local/design/usability-slow-network.json',JSON.stringify({latency_ms:200,download_bytes_per_second:384000,upload_bytes_per_second:192000,measured_journey_ms:Date.now()-started,financial_mutations:0,scope:'One read-only local built-runtime journey with browser network emulation; not a production bandwidth or capacity guarantee.'},null,2));
 await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
});
