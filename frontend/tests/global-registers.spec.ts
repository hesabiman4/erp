import {test,expect} from '@playwright/test';
import {readFile,mkdir} from 'node:fs/promises';
test.setTimeout(300000);
test('whole-result sales and stock registers paginate, search beyond page one and keep empty filters usable',async({page})=>{
 test.skip(process.env.ERP_DEMO_E2E!=='1','Synthetic workflow requires isolated QA.');expect(process.env.ERP_E2E_BASE_URL).toContain(':5174');
 const secret=JSON.parse(await readFile('../.local/verify_ui_20261029-credentials.json','utf8'));
 await page.goto('/');await page.locator('[name=username]').fill('owner');await page.locator('[name=password]').fill(secret.owner);await page.locator('[type=submit]').click();await expect(page.locator('.sidebar')).toBeVisible();
 const original=await page.locator('.business-switch select').inputValue();
 const f=await page.evaluate(async original=>{
  let business=original;const token=decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.slice(10)||'');
  const call=async(path:string,body?:any)=>{const r=await fetch(path,{method:body?'POST':'GET',headers:{'X-Business-ID':business,'X-CSRFToken':token,'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},body:body?JSON.stringify(body):undefined});const data=await r.json();if(!r.ok)throw Error(JSON.stringify(data));return data;};
  const stamp=Date.now();business=String((await call('/api/businesses/',{name:'QA global register '+stamp,slug:'qa-global-register-'+stamp,location_name:'Training Herat'})).id);const c=await call('/api/catalog/'),wh=c.warehouses[0],date=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kabul'}).format(new Date());
  const base=await call('/api/catalog/products/',{code:'BASE',name:'Training base adhesive',kind:'finished',line:'adhesive',unit:'kg',price:'1'});const products=[];
  for(let i=1;i<=105;i++)products.push(await call('/api/catalog/products/',{code:`AD-${String(i).padStart(3,'0')}`,name:`Training adhesive ${String(i).padStart(3,'0')}`,kind:'finished',line:'adhesive',unit:'kg',price:'1'}));
  await call('/api/operations/stock_opening/',{date,warehouse:wh.id,reason:'Synthetic global-register acceptance',lines:[{product:base.id,quantity:'500',value:'500'},...products.map((p:any,i)=>({product:p.id,quantity:String(i+1),value:String(i+1)}))]});
  const sales=[];for(let i=1;i<=105;i++)sales.push((await call('/api/operations/sale/',{date,warehouse:wh.id,customer_name:'Training walk-in',paid:'0',lines:[{product:base.id,quantity:'1',unit_price:String(i)}]})).document);
  return{business,sales};
 },original);
 await page.reload();await page.locator('.business-switch select').selectOption(f.business);await page.locator('.language-select').selectOption('en');await page.goto('/sales');
 const register=page.locator('.document-register'),grid=register.locator('.data-grid');await expect(grid.locator('tbody tr')).toHaveCount(100);await expect(register.locator('.summary-strip')).toContainText('5,565');
 await grid.getByRole('combobox',{name:'Sort',exact:true}).selectOption('amount');await expect(grid.locator('tbody tr').first()).toContainText(f.sales[0].number);await expect(grid.locator('tfoot')).toContainText('5,050');
 await register.getByRole('button',{name:'Next page',exact:true}).click();await expect(grid.locator('tbody tr')).toHaveCount(5);await expect(grid.locator('tbody tr').first()).toContainText(f.sales[100].number);await expect(register.locator('.summary-strip')).toContainText('5,565');
 const search=grid.getByRole('textbox',{name:'Search all authorized documents',exact:true});await search.fill(f.sales[0].number);await expect(grid.locator('tbody tr')).toHaveCount(1);await expect(grid.locator('tbody tr')).toContainText(f.sales[0].number);
 await search.fill('NO_MATCH_TRAINING');await expect(grid.locator('tbody tr')).toHaveCount(0);await expect(search).toBeVisible();await expect(register).toContainText('No documents match these filters.');await search.fill('');await expect(grid.locator('tbody tr')).toHaveCount(100);
 await page.goto('/inventory');await page.locator('.inventory-toolbar button').filter({hasText:'All stock'}).click();const stock=page.locator('.inventory-register');await expect(stock.locator('.data-grid').first().locator('tbody tr')).toHaveCount(100);await expect(stock.locator('.summary-strip')).toContainText('5,960');
 const stockSearch=stock.getByRole('textbox',{name:'Search all authorized stock',exact:true});await stockSearch.fill('AD-105');await expect(stock.locator('.data-grid').first().locator('tbody tr')).toHaveCount(1);await expect(stock.locator('.summary-strip')).toContainText('105');
 await page.locator('.language-select').selectOption('ps');await expect(page.locator('html')).toHaveAttribute('dir','rtl');await page.locator('.language-select').selectOption('fa');await expect(page.locator('html')).toHaveAttribute('dir','rtl');
 await mkdir('../.local/design/roadmap-v8',{recursive:true});await page.screenshot({path:'../.local/design/roadmap-v8/global-stock-dari.png',fullPage:true});
});
