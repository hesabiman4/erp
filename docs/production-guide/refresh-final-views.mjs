/** Read-only final-state captures; never re-create historical intermediate states. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const require=createRequire(path.join(root,'frontend/package.json'));
const {chromium,expect}=require('@playwright/test');
const folder=path.join(root,'.local/production_guide_20261123');
const credentials=JSON.parse(fs.readFileSync(path.join(folder,'credentials.json')));
const state=JSON.parse(fs.readFileSync(path.join(folder,'progress.json')));
const browser=await chromium.launch({channel:'msedge',headless:true});
try{
 const page=await browser.newPage({viewport:{width:1280,height:900},deviceScaleFactor:1.5});
 const marker=await(await page.request.get('http://localhost:8083/guide-info/')).json();
 if(!marker.synthetic_only||marker.database!=='verify_production_guide_20261123'||credentials.database!==marker.database||!state.finished)throw Error('Not the completed guide fixture.');
 await page.goto('http://localhost:8083/');
 await page.locator('[name=username]').fill(credentials.username);
 await page.locator('[name=password]').fill(credentials.password);
 await page.locator('[type=submit]').click();
 await page.locator('.business-switch select').selectOption(String(state.business));
 await page.locator('.language-select').selectOption('fa');
 await page.locator('.calendar-select').selectOption('jalali');
 await page.goto('http://localhost:8083/inventory');
 const card=page.locator('.block-card');
 await expect(card).toContainText('گدام فروش هرات');
 await card.screenshot({path:path.join(root,'docs/production-guide/images/35-herat-ready-screen.png'),animations:'disabled'});
 await page.getByRole('button',{name:'تمام موجودی',exact:true}).click();
 await page.waitForLoadState('networkidle');
 const register=page.locator('.inventory-register');
 await expect(register).toContainText('۳۴٬۵۰۰');
 await expect(register.locator('tbody tr').first()).toBeVisible();
 await register.scrollIntoViewIfNeeded();
 const box=await register.boundingBox();
 const files=[];
 for(const [part,start,end] of [['stock-01',0,Math.ceil(box.height*.55)],['stock-02',Math.floor(box.height*.45),box.height]]){
  const file=`40-final-stock-${part}.png`;
  await page.screenshot({path:path.join(root,'docs/production-guide/images',file),clip:{x:box.x,y:box.y+start,width:box.width,height:end-start},animations:'disabled'});
  files.push({id:'40-final-stock',title:'موجودی نهایی اسفنج، چسپ، مواد و فرآورده‌های جانبی',file,part,url:'/inventory',synthetic_only:true});
 }
 state.captures=state.captures.filter(row=>row.id!=='40-final-stock').concat(files);
 fs.writeFileSync(path.join(folder,'progress.json'),JSON.stringify(state,null,2));
 const manifestPath=path.join(root,'docs/production-guide/capture-manifest.json');
 const manifest=JSON.parse(fs.readFileSync(manifestPath));manifest.captures=state.captures;
 fs.writeFileSync(manifestPath,JSON.stringify(manifest,null,2));
 console.log('Refreshed actual final-state views; stock table split for legibility. No financial writes.');
}finally{await browser.close();}
