import {test,expect} from '@playwright/test';
import {readFile,mkdir} from 'node:fs/promises';

test.setTimeout(240000);
test.beforeEach(async()=>{
 test.skip(process.env.ERP_DEMO_E2E!=='1','Localization acceptance uses the isolated QA server.');
 expect(process.env.ERP_E2E_BASE_URL).toContain(':5174');
});
async function login(page:any){
 const credentials=JSON.parse(await readFile(process.env.ERP_E2E_CREDENTIALS||'../.local/verify_ui_20261029-credentials.json','utf8'));
 await page.goto('/');await page.locator('[name=username]').fill('owner');await page.locator('[name=password]').fill(credentials.owner);await page.locator('[type=submit]').click();await expect(page.locator('.sidebar')).toBeVisible();
}

test('Dari remains the default and login labels, placeholders and direction switch before authentication',async({page})=>{
 await page.goto('/');await expect(page.locator('.login-language select')).toHaveValue('fa');await expect(page.locator('html')).toHaveAttribute('dir','rtl');await expect(page.getByRole('heading',{name:'خوش آمدید',exact:true})).toBeVisible();
 await page.locator('.login-language select').selectOption('en');await expect(page.locator('html')).toHaveAttribute('dir','ltr');await expect(page.getByRole('heading',{name:'Welcome',exact:true})).toBeVisible();await expect(page.locator('[name=username]')).toHaveAttribute('placeholder','Your username');await expect(page.getByRole('button',{name:'Sign in',exact:true})).toBeVisible();await expect(page).toHaveTitle('Nawa | Accounting & manufacturing');
 await page.locator('[name=username]').fill('typed-account');await page.locator('.login-language select').selectOption('ps');await expect(page.locator('html')).toHaveAttribute('dir','rtl');await expect(page.getByRole('heading',{name:'ښه راغلاست',exact:true})).toBeVisible();await expect(page.locator('[name=username]')).toHaveValue('typed-account');await expect(page.getByRole('button',{name:'ننوتل',exact:true})).toBeVisible();await expect(page.locator('[name=username]')).toHaveAttribute('placeholder','ستاسو کارن نوم');
 await mkdir('../.local/design/localization-screens',{recursive:true});await page.screenshot({path:'../.local/design/localization-screens/login-pashto.png',fullPage:true});await page.reload();await expect(page.locator('.login-language select')).toHaveValue('ps');await expect(page.locator('html')).toHaveAttribute('lang','ps-AF');
});

test('setup and production forms translate captions while stored category and item identifiers stay intact',async({page})=>{
 await login(page);const writes:string[]=[];page.on('request',r=>{if(r.method()!=='GET'&&/\/api\/(operations|documents|catalog|businesses)\//.test(r.url()))writes.push(r.url());});
 const originals=await page.locator('.business-switch select option').allTextContents();
 for(const language of ['en','ps']){
  await page.goto('/settings');await page.locator('.language-select').selectOption(language);await expect(page.locator('html')).toHaveAttribute('dir',language==='en'?'ltr':'rtl');
  await page.locator('.setting-tabs').getByRole('button',{name:language==='en'?'Employees':'کارکوونکي',exact:true}).click();await page.locator('.access-toolbar button.primary').click();
  await expect(page.locator('.modal h2')).not.toHaveText('افزودن کارمندان');await expect(page.locator('.modal select[name=kind] option[value=weekly]')).toHaveText(language==='en'?'Weekly':'اوونیز');
  await page.locator('.modal select[name=kind]').selectOption('weekly');await expect(page.locator('.modal select[name=kind]')).toHaveValue('weekly');await page.locator('.modal input[name=name]').fill('آزمایشی — unchanged');await expect(page.locator('.modal input[name=name]')).toHaveValue('آزمایشی — unchanged');await page.keyboard.press('Escape');
  await page.goto('/production');await page.getByRole('button',{name:language==='en'?'Record production batch':'د تولید جوپه ثبتول',exact:true}).click();await expect(page.locator('.modal')).toBeVisible();await expect(page.locator('.modal')).toContainText(language==='en'?'Record only materials actually consumed.':'یوازې واقعاً مصرف شوي مواد ثبت کړئ.');
  const output=page.locator('.modal select[name="output-0"]');const choices=await output.locator('option').allTextContents();expect(choices.some(text=>text.includes('45')||text.includes('۴۵'))).toBe(true);await page.keyboard.press('Escape');
  await expect(page.locator('.business-switch select option')).toHaveText(originals);
 }
 expect(writes).toEqual([]);await page.locator('.language-select').selectOption('fa');
});

test('new operational screens and advanced captions render English and Pashto without posting',async({page})=>{
 await login(page);const writes:string[]=[];page.on('request',r=>{if(r.method()!=='GET'&&/\/api\/(operations|documents|captures)\//.test(r.url()))writes.push(r.url());});
 const cases=[
  ['onboarding','Guided business onboarding','د پیل پړاو په پړاو لارښود'],
  ['crm','Opportunities and sales follow-up','فرصتونه او د پلور تعقیب'],
  ['capture','Receipt and bill capture','د رسیدونو سکین او څېړنه'],
  ['statements','Statement import and matching','د صورت حساب واردول او تطبیق'],
  ['sourcing','Supplier quotations','د پېرود وړاندیزونه پرتله کول'],
  ['runtime_management','Release, installation and recovery','نسخه، چلول او بېرته راګرځول'],
  ['jobs','Projects & dedicated job costing','پروژه او د فرمایشي کار لګښت'],
  ['accounting_extensions','Commission on collected net sales','د ترلاسه شوي خالص پلور پر بنسټ کمېشن'],
 ];
 for(const language of ['en','ps']){
  await page.locator('.language-select').selectOption(language);
  for(const [view,en,ps] of cases){
   await page.goto(`/operations?view=${view}`);await expect(page.locator('.growth-content')).toBeVisible();await expect(page.getByRole('heading',{name:language==='en'?en:ps,exact:true})).toBeVisible();await expect(page.locator('html')).toHaveAttribute('dir',language==='en'?'ltr':'rtl');
  }
  await page.goto('/operations?view=replenishment');await expect(page.locator('.growth-content .panel-header p')).toContainText(language==='en'?'Current physical stock minus reservations':'اوسنۍ فزیکي زېرمه منفي رزرو');
 }
 await mkdir('../.local/design/localization-screens',{recursive:true});await page.goto('/operations?view=onboarding');await expect(page.getByRole('heading',{name:'د پیل پړاو په پړاو لارښود',exact:true})).toBeVisible();await page.screenshot({path:'../.local/design/localization-screens/onboarding-pashto.png',fullPage:true});expect(writes).toEqual([]);await page.locator('.language-select').selectOption('fa');
});
