import i18n from './i18n';
const copy:[string,string,string][]=[
 ['خلاصه سند هنگام ثبت','Document summary at posting','د ثبت پر مهال د سند لنډیز'],
 ['این مبالغ مربوط به زمان ثبت همین سند است؛ مانده فعلی در بالای صفحه و دریافت‌ها و برگشت‌های بعدی در اسناد مرتبط دیده می‌شود.','These amounts describe this document when it was posted. The current balance is shown above; later collections and returns appear in linked documents.','دا مبلغونه د همدې سند د ثبت د وخت دي. اوسنۍ پاتې د پاڼې په سر کې ده؛ وروسته ترلاسه شوې پیسې او بېرته ستنول په تړلو سندونو کې ښکاري.'],
 ['دریافت / پرداخت هنگام ثبت','Received / paid at posting','د ثبت پر مهال ترلاسه / ورکړل شوې پیسې'],
 ['مانده هنگام ثبت','Balance at posting','د ثبت پر مهال پاتې'],
 ['اعتبار ایجادشده هنگام ثبت','Credit created at posting','د ثبت پر مهال جوړ شوی اعتبار'],
];
i18n.addResourceBundle('en','translation',Object.fromEntries(copy.map(([fa,en])=>[fa,en])),true,true);
i18n.addResourceBundle('ps','translation',Object.fromEntries(copy.map(([fa,,ps])=>[fa,ps])),true,true);
