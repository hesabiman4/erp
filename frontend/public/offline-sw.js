/* Cache public app-shell assets only. Never cache authenticated API, admin,
   attachments, print views, POSTs, or cross-origin requests. Opt-in registration. */
const CACHE='nawa-shell-v1';
const isPublicAsset=path=>path.startsWith('/assets/')||['/manifest.webmanifest','/offline-shell.html','/app-icon.svg'].includes(path);
async function refreshShell(){const cache=await caches.open(CACHE);const response=await fetch('/',{credentials:'omit',cache:'reload'});if(!response.ok||!(response.headers.get('Content-Type')||'').includes('text/html'))return;const html=await response.clone().text();const urls=[...html.matchAll(/(?:src|href)="(\/assets\/[^"#]+)"/g)].map(match=>match[1]);await Promise.all(urls.map(async url=>{const asset=await fetch(url,{credentials:'omit'});if(asset.ok)await cache.put(url,asset);}));await cache.put('/',response);}
self.addEventListener('install',event=>event.waitUntil((async()=>{const cache=await caches.open(CACHE);await cache.addAll(['/offline-shell.html','/manifest.webmanifest','/app-icon.svg']);await refreshShell();await self.skipWaiting();})()));
self.addEventListener('activate',event=>event.waitUntil((async()=>{for(const key of await caches.keys())if(key.startsWith('nawa-shell-')&&key!==CACHE)await caches.delete(key);await self.clients.claim();})()));
self.addEventListener('fetch',event=>{const request=event.request;const url=new URL(request.url);if(request.method!=='GET'||url.origin!==self.location.origin||url.pathname.startsWith('/api/')||url.pathname.startsWith('/admin/'))return;
 if(isPublicAsset(url.pathname)){event.respondWith((async()=>{const cache=await caches.open(CACHE);const cached=await cache.match(request);if(cached)return cached;const response=await fetch(request);if(response.ok)await cache.put(request,response.clone());return response;})());return;}
 if(request.mode==='navigate'){event.respondWith((async()=>{try{const response=await fetch(request);if(!response.ok)throw new Error('Unavailable');await refreshShell().catch(()=>{});return response;}catch{const cache=await caches.open(CACHE);return await cache.match('/')||await cache.match('/offline-shell.html')||Response.error();}})());}
});
