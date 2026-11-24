import i18n from './i18n';
const copy:[string,string,string][]=[
 ['جستجو در تمام موجودی مجاز','Search all authorized stock','په ټولو اجازه لرونکو زېرمو کې لټون'],
 ['پاک‌کردن فیلترها','Clear filters','چاڼونه پاک کړئ'],
 ['جستجوی متنی ذخیره نمی‌شود. فقط ستون‌ها، ترتیب و فیلترهای مجاز ذخیره می‌شوند.','Search text is not stored. Only columns, sort order and permitted filters are saved.','د لټون متن نه ساتل کېږي. یوازې ستنې، ترتیب او اجازه لرونکي چاڼونه ساتل کېږي.'],
 ['گروه‌های موجودی مطابق فیلتر','Matching stock pools','برابر د زېرمو ډلې'],
 ['ارزش تمام موجودی مجاز مطابق فیلتر','Value of all matching authorized stock','د ټولو برابرو اجازه لرونکو زېرمو ارزښت'],
 ['مجموع مقدار بر اساس محصول و اندازه','Quantities by product and footprint','مقدارونه د توکي او اندازې له مخې'],
 ['مقادیر هر محصول، واحد و اندازه جدا جمع می‌شود؛ این ارقام تضمین مناسب‌بودن قطعات برای یک برش نیست.','Each product, unit and footprint is totalled separately; these figures do not guarantee a feasible physical cut.','هر توکی، واحد او اندازه جلا جمع کېږي؛ دا شمېرې د عملي پرېکولو تضمین نه کوي.'],
 ['دارای موجودی','In stock','زېرمه لري'],['بدون موجودی','Out of stock','زېرمه نشته'],
 ['کار با تمام نتایج مجاز','Work with all authorized results','له ټولو اجازه لرونکو پایلو سره کار'],
 ['جستجو در تمام اسناد مجاز','Search all authorized documents','په ټولو اجازه لرونکو سندونو کې لټون'],
 ['جستجو و ترتیب برای تمام نتایج مجاز است؛ مجموع پایین جدول فقط برای صفحه جاری است.','Search and sorting cover all authorized results; the table footer totals only the current page.','لټون او ترتیب ټولې اجازه لرونکې پایلې رانغاړي؛ د جدول لاندې مجموعه یوازې د اوسني مخ ده.'],
 ['سندی مطابق فیلترهای انتخاب‌شده نیست.','No documents match these filters.','له دې چاڼونو سره برابر سند نشته.'],
 ['تمام اسناد مطابق فیلتر','All matching documents','ټول برابر سندونه'],
 ['مبلغ تمام نتایج مجاز','Amount across all authorized results','د ټولو اجازه لرونکو پایلو مبلغ'],
 ['مانده تمام نتایج مجاز','Balance across all authorized results','د ټولو اجازه لرونکو پایلو پاتې'],
 ['وضعیت سند','Document status','د سند حالت'],
 ['وضعیت پرداخت','Payment status','د ورکړې حالت'],
 ['قسمی پرداخت‌شده','Partially paid','یوه برخه ورکړل شوې'],
 ['در حال تازه‌سازی نتایج؛ ارقام قبلی تا پایان بررسی نمایش داده می‌شود.','Updating results; previous figures remain visible until the check completes.','پایلې تازه کېږي؛ پخواني شمېرې د کتنې تر بشپړېدو ښکاري.'],
];
i18n.addResourceBundle('en','translation',Object.fromEntries(copy.map(([fa,en])=>[fa,en])),true,true);
i18n.addResourceBundle('ps','translation',Object.fromEntries(copy.map(([fa,,ps])=>[fa,ps])),true,true);
