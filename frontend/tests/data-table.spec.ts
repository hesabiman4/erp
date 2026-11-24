import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';

test.setTimeout(240000);
test('real table sorting, exact loaded totals, private scoped views and audited master edits work without changing posted sales',async({page})=>{
 test.skip(process.env.ERP_DEMO_E2E!=='1','Table acceptance creates isolated synthetic QA businesses.');
 expect(process.env.ERP_E2E_BASE_URL).toContain(':5174');
 const credentials=JSON.parse(await readFile(process.env.ERP_E2E_CREDENTIALS||'../.local/verify_ui_20261029-credentials.json','utf8'));
 await page.goto('/');await page.locator('[name=username]').fill('owner');await page.locator('[name=password]').fill(credentials.owner);await page.locator('[type=submit]').click();await expect(page.locator('.sidebar')).toBeVisible();
 const original=await page.locator('.business-switch select').inputValue();
 const fixture=await page.evaluate(async original=>{
  const csrf=decodeURIComponent(document.cookie.split('; ').find(value=>value.startsWith('csrftoken='))?.split('=')[1]||'');
  const request=async(path:string,body?:any,business=original)=>{const response=await fetch(path,{method:body?'POST':'GET',headers:{'X-Business-ID':business,'X-CSRFToken':csrf,'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},...(body?{body:JSON.stringify(body)}:{})});const data=await response.json();if(!response.ok)throw new Error(JSON.stringify(data));return data;};
  const stamp=Date.now();const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kabul'}).format(new Date());
  const day=(offset:number)=>{const date=new Date(today+'T12:00:00Z');date.setUTCDate(date.getUTCDate()+offset);return date.toISOString().slice(0,10);};
  const businesses=[];
  for(let index=0;index<2;index++){
   const business=await request('/api/businesses/',{name:`QA table ${stamp}-${index}`,slug:`qa-table-${stamp}-${index}`,manufacturing_mode:'actual',location_name:'Grid test location',warehouse_name:'Grid test store'});
   const id=String(business.id),catalog=await request('/api/catalog/',undefined,id);
   const product=await request('/api/catalog/products/',{code:'GRID-1',name:'Grid product one',kind:'finished',line:'adhesive',unit:'kg',price:'0.10'},id);
   const second=await request('/api/catalog/products/',{code:'GRID-2',name:'Grid product two',kind:'finished',line:'adhesive',unit:'kg',price:'0.20'},id);
   const privateName=`PRIVATE_GRID_CUSTOMER_${stamp}`;
   const customer=await request('/api/catalog/parties/',{name:privateName,kind:'customer',phone:'0700000000'},id);
   await request('/api/operations/stock_opening/',{date:day(-10),warehouse:catalog.warehouses[0].id,reason:'Synthetic table acceptance',lines:[{product:product.id,quantity:'100',value:'1'}]},id);
   const sales=[];
   for(const [line,price] of (index?['5.00']:['0.10','0.20','1.10','1.20','10.05','2.10']).entries())sales.push((await request('/api/operations/sale/',{date:day(-6+line),warehouse:catalog.warehouses[0].id,party:customer.id,paid:'0',lines:[{product:product.id,quantity:'1',unit_price:price}]},id)).document);
   businesses.push({id,product:product.id,second:second.id,privateName,sales});
  }
  return businesses;
 },original);
 await page.reload();await page.locator('.business-switch select').selectOption(fixture[0].id);await page.locator('.language-select').selectOption('en');await page.goto('/sales');
 const grid=page.locator('[data-table-key="documents:sale"]');await expect(grid).toBeVisible();await expect(grid.locator('tbody tr')).toHaveCount(6);
 await expect(grid.locator('tfoot td[data-label="Amount"]')).toContainText('14.75');
 await grid.getByRole('combobox',{name:'Sort',exact:true}).selectOption('amount');
 const numbers=()=>grid.locator('tbody .document-number').allTextContents();
 await expect.poll(numbers).toEqual([0,1,2,3,5,4].map(index=>fixture[0].sales[index].number));
 await grid.getByRole('button',{name:'Ascending',exact:true}).click();await expect.poll(numbers).toEqual([4,5,3,2,1,0].map(index=>fixture[0].sales[index].number));
 await grid.getByRole('combobox',{name:'Sort',exact:true}).selectOption('date');await expect.poll(numbers).toEqual(fixture[0].sales.map((sale:any)=>sale.number));
 await expect(grid.locator('tbody .inline-edit-cell button')).toHaveCount(0);
 await grid.locator('summary').filter({hasText:'Visible columns'}).click();await grid.getByRole('checkbox',{name:'Account party',exact:true}).uncheck();await grid.locator('summary').filter({hasText:'Visible columns'}).click();await expect(grid.getByRole('columnheader',{name:'Account party',exact:true})).toHaveCount(0);
 await grid.getByRole('textbox',{name:'Search all authorized documents',exact:true}).fill(fixture[0].privateName);await grid.getByRole('button',{name:'Save current view',exact:true}).click();
 const saved=await grid.getByRole('combobox',{name:'Saved view',exact:true}).inputValue();expect(saved).toMatch(/^view-/);
 const stored=await page.evaluate(()=>Object.entries(localStorage).filter(([key])=>key.startsWith('nawa:grid:2:')));expect(stored.length).toBeGreaterThan(0);expect(JSON.stringify(stored)).not.toContain(fixture[0].privateName);expect(JSON.stringify(stored)).not.toContain(fixture[0].sales[0].number);expect(JSON.stringify(stored)).not.toContain('14.75');
 await page.reload();await expect(grid).toBeVisible();await expect(grid.getByRole('textbox',{name:'Search all authorized documents',exact:true})).toHaveValue('');await expect(grid.getByRole('columnheader',{name:'Account party',exact:true})).toHaveCount(0);await grid.getByRole('combobox',{name:'Saved view',exact:true}).selectOption(saved);
 await page.locator('.business-switch select').selectOption(fixture[1].id);await expect(grid.locator('tbody tr')).toHaveCount(1);await expect(grid.getByRole('columnheader',{name:/Account party/})).toHaveCount(1);await expect(grid.getByRole('combobox',{name:'Saved view',exact:true}).locator('option')).toHaveCount(1);
 await page.locator('.business-switch select').selectOption(fixture[0].id);await page.goto('/settings');
 const master=page.locator('[data-table-key="catalog:products"]');await expect(master).toBeVisible();await expect(master.locator('tbody tr').filter({hasText:'GRID-1'})).toBeVisible();
 await master.locator('tbody tr').filter({hasText:'GRID-1'}).getByRole('button',{name:'Edit in row',exact:true}).click();await expect(master.locator('.inline-row-form')).toBeVisible();await expect(page.locator('.modal')).toHaveCount(0);
 await master.locator('.inline-row-form [name=name]').fill('Grid product one updated');await master.locator('.inline-row-form [name=price]').fill('۹٫۹۹');
 const patched=page.waitForResponse(response=>response.url().endsWith(`/api/catalog/products/${fixture[0].product}/`)&&response.request().method()==='PATCH');await master.getByRole('button',{name:'Save row',exact:true}).click();expect((await patched).status()).toBe(200);await expect(master.locator('.inline-row-form')).toHaveCount(0);await expect(master.locator('tbody tr').filter({hasText:'GRID-1'})).toContainText('Grid product one updated');
 await master.getByRole('checkbox',{name:'Select eligible rows on this page',exact:true}).check();await master.getByRole('button',{name:/Deactivate selected/}).click();await expect(master.getByRole('region',{name:'Review bulk action',exact:true})).toBeVisible();
 await master.getByRole('button',{name:'Cancel action',exact:true}).click();await expect(master.getByRole('region',{name:'Review bulk action',exact:true})).toHaveCount(0);
 await master.getByRole('button',{name:/Deactivate selected/}).click();await master.getByRole('button',{name:'Confirm action',exact:true}).click();await expect(master.locator('.data-grid-bulk')).toHaveCount(0);
 const verified=await page.evaluate(async fixture=>{const headers={'X-Business-ID':fixture.id};const catalog=await fetch('/api/catalog/',{headers}).then(r=>r.json());const original=await fetch(`/api/documents/${fixture.sales[0].id}/`,{headers}).then(r=>r.json());return {products:catalog.products,original};},fixture[0]);
 expect(verified.products.find((p:any)=>p.id===fixture[0].product).price).toBe('9.990000');expect(verified.products.filter((p:any)=>[fixture[0].product,fixture[0].second].includes(p.id)).every((p:any)=>p.active===false)).toBe(true);expect(verified.original.amount).toBe('0.10');expect(verified.original.state).toBe('posted');
 await page.locator('.business-switch select').selectOption(original);await page.locator('.language-select').selectOption('fa');
});
