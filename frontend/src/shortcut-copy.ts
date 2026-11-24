import i18n from './i18n';
const copy:[string,string,string][]=[
 ['میانبرهای صفحه‌کلید','Keyboard shortcuts','د کیبورډ لنډلارې'],
 ['میانبرها هنگام باز بودن فورم فعال نیستند.','Shortcuts are inactive while a form is open.','د فورم د پرانیستې پر مهال لنډلارې فعالې نه دي.'],
];
i18n.addResourceBundle('en','translation',Object.fromEntries(copy.map(([fa,en])=>[fa,en])),true,true);
i18n.addResourceBundle('ps','translation',Object.fromEntries(copy.map(([fa,,ps])=>[fa,ps])),true,true);
