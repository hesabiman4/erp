import {test,expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {mkdir} from 'node:fs/promises';
import {dailyShortcut} from '../src/keyboard-shortcuts';
const event=(key:string,options:Record<string,unknown>={})=>({key,code:key.length===1?'Key'+key.toUpperCase():key,altKey:false,ctrlKey:false,metaKey:false,shiftKey:false,repeat:false,isComposing:false,defaultPrevented:false,...options});

test('search and operation keys are whitelisted and respect keyboard state',()=>{
 for(const route of ['/purchases','/transfers','/','/accounting']){
  expect(dailyShortcut(event('k',{ctrlKey:true}),route)).toBe('search');
  expect(dailyShortcut(event('f',{altKey:true}),route)).toBe('search');
  expect(dailyShortcut(event('F4',{altKey:true}),route)).toBeNull();
  for(const flag of ['shiftKey','metaKey','repeat','isComposing','defaultPrevented'])expect(dailyShortcut(event('k',{ctrlKey:true,[flag]:true}),route)).toBeNull();
 }
 expect(dailyShortcut(event('ن',{code:'KeyK',ctrlKey:true}),'/purchases')).toBe('search');
 expect(dailyShortcut(event('n',{altKey:true}),'/purchases')).toBe('purchase_receive');
 expect(dailyShortcut(event('r',{altKey:true}),'/purchases')).toBe('supplier_payment');
 expect(dailyShortcut(event('n',{altKey:true}),'/transfers')).toBe('transfer_dispatch');
 expect(dailyShortcut(event('r',{altKey:true}),'/transfers')).toBe('transfer_receive');
 expect(dailyShortcut(event('n',{altKey:true}),'/accounting')).toBeNull();
 expect(dailyShortcut(event('k',{ctrlKey:true,altKey:true}),'/purchases')).toBeNull();
 expect(dailyShortcut(event('n'),'/purchases')).toBeNull();
});
test('runtime source has no reserved window-close binding or hint',()=>{
 const result=JSON.parse(execFileSync(process.execPath,['../scripts/check_shortcuts.cjs'],{encoding:'utf8'}));
 expect(result.checked_source_files).toBeGreaterThan(50);expect(result.forbidden_window_shortcuts).toEqual([]);
});

test('real RTL purchase and transfer screens support search, help and modal isolation',async({page})=>{
 test.setTimeout(120000);
 const username=process.env.ERP_E2E_USERNAME,password=process.env.ERP_E2E_PASSWORD;
 test.skip(!username||!password,'Explicit isolated training credentials required for browser acceptance.');
 await page.goto('/');await page.locator('input[name=username]').fill(username!);await page.locator('input[name=password]').fill(password!);await page.locator('button[type=submit]').click();
 await expect(page.locator('.business-switch')).toBeVisible();await page.locator('.language-select').selectOption('fa');
 for(const route of ['/purchases','/transfers']){
  await page.goto(route);const help=page.locator('.shortcut-help');await expect(help).toBeVisible();
  const localSearch=page.locator('.document-register .data-grid-search input').first();await expect(localSearch).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('dir','rtl');
  await expect(help.locator('.shortcut-help-panel')).not.toBeVisible();
  await help.locator('summary').click();await expect(help.locator('.shortcut-help-panel')).toBeVisible();
  await mkdir('../.local/audit_20261122',{recursive:true});await page.screenshot({path:`../.local/audit_20261122/shortcuts-${route.slice(1)}.png`,fullPage:true});
  await page.keyboard.press('Escape');await expect(help).not.toHaveAttribute('open','');await expect(help.locator('summary')).toBeFocused();
  await page.keyboard.press('Control+k');const focused=page.locator('.workspace .data-grid-search input:focus,.workspace .global-search input:focus');await expect(focused).toHaveCount(1);await expect(localSearch).toBeFocused();
  await page.keyboard.press('Alt+f');await expect(focused).toHaveCount(1);
  await page.keyboard.press('Alt+n');await expect(page.locator('.modal')).toBeVisible();const field=page.locator('.modal input:focus,.modal select:focus');await expect(field).toHaveCount(1);await page.keyboard.press('Control+k');await expect(field).toHaveCount(1);await page.keyboard.press('Escape');await expect(page.locator('.modal')).toHaveCount(0);
 }
 await page.goto('/');await expect(page.locator('.global-search input')).toBeVisible();await page.keyboard.press('Control+k');await expect(page.locator('.workspace .data-grid-search input:focus,.workspace .global-search input:focus')).toHaveCount(1);
});
