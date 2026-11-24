import {test,expect} from '@playwright/test';
import {readFile,writeFile,mkdir,readdir,unlink} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';

test.setTimeout(300000);
test('host Settings chooses a folder, reviews and creates an encrypted backup, and scheduler uses that configuration',async({page})=>{
 test.skip(process.env.ERP_DEMO_E2E!=='1','Host backup checks are restricted to the isolated QA installation.');
 expect(process.env.ERP_E2E_BASE_URL).toContain(':5174');
 const root=resolve('..'),database='verify_ui_20261029',tag=createHash('sha256').update(database).digest('hex').slice(0,12);
 const configuration=resolve(root,'.local',`backup-settings-${tag}.json`),destination=resolve(root,'.local','qa-backup-settings-v6');
 let previous:Buffer|undefined;try{previous=await readFile(configuration);}catch(e:any){if(e.code!=='ENOENT')throw e;}
 await mkdir(destination,{recursive:true});const before=new Set(await readdir(destination));
 const credentials=JSON.parse(await readFile(resolve(root,'.local','verify_ui_20261029-credentials.json'),'utf8'));
 try{
  await page.goto('/');await page.locator('[name=username]').fill('owner');await page.locator('[name=password]').fill(credentials.owner);await page.locator('[type=submit]').click();await expect(page.locator('.sidebar')).toBeVisible();await page.locator('.language-select').selectOption('en');await page.goto('/settings?section=security');
  const panel=page.locator('.panel').filter({has:page.getByRole('heading',{name:'Encrypted backups',exact:true})});
  await panel.getByRole('textbox',{name:'Backup destination folder',exact:true}).fill(destination);
  await panel.locator('input[inputmode=numeric]').fill('12');
  const saved=page.waitForResponse(r=>r.url().endsWith('/api/backup-settings/')&&r.request().method()==='POST');await panel.getByRole('button',{name:'Save and test folder',exact:true}).click();expect((await saved).status()).toBe(200);await expect(panel).toContainText('Destination configured');
  await page.reload();await expect(panel.locator('input[inputmode=numeric]')).toHaveValue('12');await expect(panel.getByRole('textbox',{name:'Backup destination folder',exact:true})).toHaveValue(destination);
  let backupWrites=0;page.on('request',r=>{if(r.url().endsWith('/api/backup-settings/')&&r.postDataJSON()?.action==='backup_now')backupWrites++;});
  await panel.getByRole('button',{name:'Back up now',exact:true}).click();await expect(page.locator('.review-action')).toBeVisible();await page.locator('.review-action .button.secondary').click();expect(backupWrites).toBe(0);
  await panel.getByRole('button',{name:'Back up now',exact:true}).click();const created=page.waitForResponse(r=>r.url().endsWith('/api/backup-settings/')&&r.request().method()==='POST');await page.locator('.review-action .button.primary').click();const response=await created,result=await response.json();expect(response.status(),JSON.stringify(result)).toBe(200);expect(result).toMatchObject({state:'succeeded',archive_verified:true,database_restore_verified:false,off_device_verified:false});
  await expect(panel).toContainText('Encrypted backup created and archive contents verified');expect(backupWrites).toBe(1);
  const createdFiles=(await readdir(destination)).filter(name=>!before.has(name));expect(createdFiles).toHaveLength(1);expect(createdFiles[0]).toMatch(/\.fernet$/);expect((await readFile(resolve(destination,createdFiles[0]),'utf8')).startsWith('gAAAA')).toBe(true);
  const tick=await promisify(execFile)(resolve(root,'.venv','Scripts','python.exe'),['backend/manage.py','run_maintenance'],{cwd:root,env:{...process.env,PGDATABASE:database},timeout:180000,maxBuffer:1024*1024});
  const status=JSON.parse(tick.stdout.trim());expect(status.backup.state).toBe('succeeded');expect(status.backup.off_device_verified).toBe(false);expect((await readdir(destination)).filter(name=>!before.has(name))).toHaveLength(1);
  await mkdir(resolve(root,'.local','design','daily-v6'),{recursive:true});await writeFile(resolve(root,'.local','design','daily-v6','settings-backup-evidence.json'),JSON.stringify({manual:result,scheduler:status.backup,qaOnly:true,mainDestinationChanged:false},null,2));
 }finally{
  if(previous)await writeFile(configuration,previous);else await unlink(configuration).catch(e=>{if(e.code!=='ENOENT')throw e;});
 }
});
