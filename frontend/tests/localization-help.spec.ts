import {test,expect} from '@playwright/test';
import {readFile,mkdir} from 'node:fs/promises';

test.setTimeout(180000);
test.beforeEach(async({page})=>{
 test.skip(process.env.ERP_DEMO_E2E!=='1','Localized acceptance uses only the isolated QA workspace.');
 expect(process.env.ERP_E2E_BASE_URL).toContain(':5174');
 const credentials=JSON.parse(await readFile(process.env.ERP_E2E_CREDENTIALS||'../.local/verify_ui_20261029-credentials.json','utf8'));
 await page.goto('/');await page.locator('[name=username]').fill('owner');await page.locator('[name=password]').fill(credentials.owner);await page.locator('[type=submit]').click();await expect(page.locator('.sidebar')).toBeVisible();
});

test('all lessons and contextual guidance have actual Pashto bodies with English and RTL switching',async({page})=>{
 const mutations:string[]=[];page.on('request',r=>{if(r.method()!=='GET'&&/\/api\/(operations|documents)\//.test(r.url()))mutations.push(r.url());});
 const business=await page.locator('.business-switch select').inputValue();
 const topics=await page.evaluate(async business=>{const response=await fetch('/api/guidance/',{headers:{'X-Business-ID':business}});if(!response.ok)throw new Error(await response.text());return (await response.json()).topics;},business);
 expect(topics).toHaveLength(7);
 await page.goto('/help?topic=sales');await page.locator('.language-select').selectOption('en');await expect(page.locator('html')).toHaveAttribute('dir','ltr');await expect(page.locator('.learning-step h3').first()).toHaveText('Check the measurement');await expect(page.locator('.learning-step p').first()).toContainText('978 mm');
 await page.locator('.language-select').selectOption('ps');await expect(page.locator('html')).toHaveAttribute('dir','rtl');await expect(page.locator('.learning-centre h1')).toHaveText('د زده کړې مرکز');
 for(const topic of topics){
  await page.locator('.learning-centre nav button').filter({hasText:topic.ps}).click();
  for(let i=0;i<topic.steps.length;i++){
   const translated=topic.steps_ps[topic.steps[i][0]];
   await expect(page.locator('.learning-step h3').nth(i)).toHaveText(translated.title);
   await expect(page.locator('.learning-step p').nth(i)).toHaveText(translated.body);
   await expect(page.locator('.learning-step p').nth(i)).toHaveAttribute('lang','ps');
  }
 }
 await mkdir('../.local/design/localization-help',{recursive:true});await page.screenshot({path:'../.local/design/localization-help/pashto-lessons.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await expect.poll(async()=>{const box=await page.locator('.sidebar').boundingBox();return !!box&&box.x>=389;}).toBe(true);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 await page.screenshot({path:'../.local/design/localization-help/pashto-phone.png',fullPage:true,animations:'disabled'});
 await page.locator('.menu-toggle').click();await expect(page.locator('.sidebar')).toHaveClass(/visible/);await page.locator('.sidebar-scrim').click({position:{x:15,y:200}});await expect(page.locator('.sidebar')).not.toHaveClass(/visible/);
 await page.locator('.language-select').selectOption('en');await expect(page.locator('html')).toHaveAttribute('dir','ltr');
 await expect.poll(async()=>{const box=await page.locator('.sidebar').boundingBox();return !!box&&box.x+box.width<=1;}).toBe(true);
 await page.locator('.menu-toggle').click();await expect(page.locator('.sidebar')).toHaveClass(/visible/);await page.locator('.sidebar-scrim').click({position:{x:375,y:200}});await expect(page.locator('.sidebar')).not.toHaveClass(/visible/);
 await page.locator('.language-select').selectOption('ps');await page.setViewportSize({width:1440,height:1000});
 await page.goto('/production');await page.locator('.contextual-guidance summary').click();await expect(page.locator('.contextual-guidance p')).toHaveText(topics.find((t:any)=>t.id==='production').steps_ps.inputs.body);
 expect(mutations).toEqual([]);await page.locator('.language-select').selectOption('fa');await expect(page.locator('html')).toHaveAttribute('dir','rtl');
});

test('advanced calendar, purchasing and closing help localizes without posting',async({page})=>{
 const mutations:string[]=[];page.on('request',r=>{if(r.method()!=='GET'&&/\/api\/(operations|documents)\//.test(r.url()))mutations.push(r.url());});
 await page.goto('/operations?view=business_periods');await page.locator('.language-select').selectOption('en');await expect(page.getByRole('heading',{name:'Business calendar and actual periods',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'Review exact month boundaries',exact:true})).toBeVisible();
 await page.locator('.language-select').selectOption('ps');await expect(page.getByRole('heading',{name:'کاري تقویم او حقیقي دورې',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'د میاشتې حقیقي پیل او پای کتل',exact:true})).toBeVisible();await expect(page.locator('.growth-content')).toContainText('د ښودلو تقویم د معاش د محاسبې له تقویم سره توپیر لري.');
 await page.goto('/operations?view=procurement');await expect(page.getByRole('heading',{name:'فرمایش، رسید او بل یو ځای وګورئ',exact:true})).toBeVisible();await page.getByRole('button',{name:'وزن او تلې',exact:true}).click();await expect(page.locator('.growth-content')).toContainText('اوسنۍ اندازې په لاس لیکل کېږي');
 await page.goto('/operations?view=closing');await expect(page.getByRole('heading',{name:'د حسابدارۍ دورې تړل',exact:true})).toBeVisible();await expect(page.locator('.growth-content')).toContainText('د کتنې ثبت حسابونه نه بدلوي.');
 await page.goto('/operations?view=advanced_planning');await expect(page.locator('.growth-content')).toContainText('د ظرفیت او حاصل پلان');await expect(page.locator('html')).toHaveAttribute('dir','rtl');
 expect(mutations).toEqual([]);await page.locator('.language-select').selectOption('fa');
});
