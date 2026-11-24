import i18n from './i18n';
const copy:[string,string,string][]=[
['مرجع پرداخت','Payment reference','د ورکړې مرجع'],
['روش دریافت','Payment method','د پیسو اخیستلو ډول'],['پرداخت چندبخشی','Split payment','وېشل شوې ورکړه'],['نوع پرداخت','Payment type','د ورکړې ډول'],['حساب واقعی دریافت','Actual receiving account','د پیسو اخیستلو اصلي حساب'],['حذف بخش پرداخت','Remove payment part','د ورکړې برخه لرې کول'],['افزودن بخش پرداخت','Add payment part','د ورکړې برخه زیاتول'],['هر مبلغ فقط در حساب واقعی همان بخش ثبت می‌شود. مانده روی همین بل باقی می‌ماند.','Each amount posts to its actual receiving account. Any unpaid balance stays on this invoice.','هر مبلغ په خپل اصلي حساب کې ثبتېږي. پاتې پور په همدې بل پاتې کېږي.']
];
i18n.addResourceBundle('en','translation',Object.fromEntries(copy.map(([fa,en])=>[fa,en])),true,true);i18n.addResourceBundle('ps','translation',Object.fromEntries(copy.map(([fa,,ps])=>[fa,ps])),true,true);
