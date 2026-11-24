import {expect} from '@playwright/test';
import type {Page} from '@playwright/test';

/** Explicitly leave the current document page or dismiss a transient form. */
export async function closeDocumentOrDialog(page:Page){
 await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
 await expect(page.locator('.workspace > .loading')).toHaveCount(0);
 const back=page.locator('.document-detail-page .document-back');
 if(await back.isVisible()){
  const previous=page.url();await back.click();await expect(page).not.toHaveURL(previous);
  if(!new URL(page.url()).pathname.startsWith('/documents/'))await expect(page.locator('.document-detail-page')).toHaveCount(0);
 }else await page.keyboard.press('Escape');
}
