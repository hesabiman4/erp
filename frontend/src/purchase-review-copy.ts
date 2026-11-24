import i18n from './i18n';
const copy:[string,string,string][]=[
 ['مشاهده سند اصلی','View original document','اصلي سند کتل'],
 ['مرور موارد باز خرید','Review open purchasing items','د پېرود د پرانیستو مواردو کتنه'],
 ['سفارش خرید دارای مانده تحویل','Purchase order awaiting delivery','د سپارلو په تمه د پېرود فرمایش'],
 ['کالای دریافت‌شده بل‌نشده','Received goods awaiting a bill','ترلاسه شوي توکي د بل په تمه'],
 ['بل تأمین‌کننده دارای مانده','Supplier bill with outstanding balance','د عرضه کوونکي بل له پاتې مبلغ سره'],
 ['ادعای باز تأمین‌کننده','Open supplier claim','د عرضه کوونکي پرانیستې ادعا'],
 ['تفاوت نرخ نیازمند بررسی','Price difference requiring review','د بیې توپیر کتنه غواړي'],
 ['گردش مرتبط خارج از دسترسی','Linked activity outside your access','تړلی فعالیت ستاسو له لاسرسي بهر دی'],
 ['این مرور موجودی یا حساب‌ها را تغییر نمی‌دهد. هر مورد را با سند اصلی بررسی کنید؛ تعداد موارد با مبلغ بدهی یکسان نیست.','This review changes no stock or accounts. Check each item against its source; item counts are not debt amounts.','دا کتنه زېرمه یا حسابونه نه بدلوي. هر مورد له اصلي سند سره وګورئ؛ د مواردو شمېر د پور مبلغ نه دی.'],
 ['شماره سند، تأمین‌کننده یا محصول','Document number, supplier or product','د سند شمېره، عرضه کوونکی یا توکی'],
 ['نوع مورد باز','Open-item type','د پرانیستي مورد ډول'],['تمام موارد مطابق فیلتر','All matching review items','ټول برابر د کتنې موارد'],
 ['مانده بل‌های همین مرور','Outstanding bills in this review','په دې کتنه کې د بلونو پاتې'],
 ['برای جلوگیری از افشای گردش محدود، مقدارها نمایش داده نمی‌شود.','Quantities are withheld because linked activity is restricted.','مقدارونه نه ښودل کېږي ځکه تړلی فعالیت محدود دی.'],
 ['بل‌کردن مانده رسید','Bill the receipt remainder','د رسید د پاتې برخې بل جوړول'],['بررسی تطبیق و ادعا','Review matching and claims','د تطبیق او ادعاوو کتنه'],
 ['خالی: مهلت پرداخت ثبت‌شده تأمین‌کننده اعمال می‌شود.','Leave blank to apply the supplier’s saved payment terms.','د عرضه کوونکي د ساتل شوو شرایطو د پلي کولو لپاره تش پرېږدئ.'],
 ['مقدار معتبر برای بل وارد کنید.','Enter a valid billing quantity.','د بل معتبر مقدار ولیکئ.'],
 ['مقدار بل از مانده بل‌نشده بیشتر شده نمی‌تواند.','Billing quantity cannot exceed the unbilled remainder.','د بل مقدار له بل نه شوې پاتې برخې زیات نه شي کېدای.'],
 ['این رسید مقدار بل‌نشده برای ثبت ندارد.','This receipt has no unbilled quantity to post.','دا رسید د ثبت لپاره بل نه شوی مقدار نه لري.'],
 ['بل فقط مانده انتخاب‌شده همین رسید را به بدهی تأمین‌کننده انتقال می‌دهد؛ موجودی دوباره وارد نمی‌شود.','The bill transfers only the selected receipt remainder to supplier payables; stock is not received again.','بل یوازې د همدې رسید ټاکل شوې پاتې برخه د عرضه کوونکي پور ته لېږدوي؛ زېرمه بیا نه ترلاسه کېږي.'],
 ['مانده بل‌نشده','Unbilled remainder','بل نه شوې پاتې برخه'],['مقدار این بل','Quantity on this bill','د دې بل مقدار'],
];
i18n.addResourceBundle('en','translation',Object.fromEntries(copy.map(([fa,en])=>[fa,en])),true,true);
i18n.addResourceBundle('ps','translation',Object.fromEntries(copy.map(([fa,,ps])=>[fa,ps])),true,true);
