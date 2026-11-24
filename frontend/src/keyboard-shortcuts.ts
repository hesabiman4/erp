/** Whitelisted physical keys also work while staff use a Dari/Pashto layout. */
export type ShortcutKey = Pick<KeyboardEvent,'key'|'code'|'altKey'|'ctrlKey'|'metaKey'|'shiftKey'|'repeat'|'isComposing'|'defaultPrevented'>;
export function dailyShortcut(event:ShortcutKey, pathname:string):string|null {
 if(event.defaultPrevented||event.repeat||event.isComposing||event.shiftKey||event.metaKey)return null;
 const key=event.code?.startsWith('Key')?event.code.slice(3).toLowerCase():event.key.toLowerCase();
 if(event.ctrlKey&&!event.altKey&&key==='k')return 'search';
 if(!event.altKey||event.ctrlKey)return null;
 if(key==='f')return 'search';
 if(pathname!=='/purchases'&&pathname!=='/transfers')return null;
 if(key==='n')return pathname==='/purchases'?'purchase_receive':'transfer_dispatch';
 if(key==='r')return pathname==='/purchases'?'supplier_payment':'transfer_receive';
 return null;
}
