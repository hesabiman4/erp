import i18n from './i18n';
const copy:[string,string,string][]=[
 ['گروه تجارتی','Trading group','سوداګریزه ډله'],['آدرس تحویل کالا','Delivery address','د توکو سپارلو پته'],
 ['شماره ثبت / نمبر تشخیصیه مالیه','Registration / tax identification number','د ثبت / مالیاتي پېژندنې شمېره'],
 ['حساب‌های احتمالاً تکراری','Possible duplicate accounts','احتمالي تکراري حسابونه'],
 ['پیش از ساخت حساب تازه، نام و تلفن را بررسی کنید. این هشدار حساب‌ها را خودکار یکجا نمی‌کند.','Review names and phone numbers before creating another account. This warning never merges accounts automatically.','د بل حساب له جوړولو مخکې نومونه او تلفنونه وګورئ. دا خبرتیا حسابونه په اتومات ډول نه یوځای کوي.'],
 ['شرایط پرداخت تأمین‌کننده','Supplier payment terms','د عرضه کوونکي د ورکړې شرایط'],['شرایط نسیه مشتری','Customer credit terms','د پېرودونکي د پور شرایط'],
 ['اشخاص تماس','Contact people','د اړیکې کسان'],['افزودن شخص تماس','Add contact person','د اړیکې کس زیاتول'],
 ['تلفن اصلی حساب برای جستجو حفظ می‌شود؛ اشخاص خرید، پرداخت و تحویل را جدا ثبت کنید.','Keep the main account phone for lookup; record purchasing, payment and delivery contacts separately.','د لټون لپاره د حساب اصلي تلفن وساتئ؛ د پېرود، ورکړې او سپارلو اړیکې جلا ثبت کړئ.'],
 ['نام شخص تماس','Contact name','د اړیکې کس نوم'],['وظیفه / مسؤولیت','Role / responsibility','دنده / مسؤولیت'],
 ['تلفن شخص تماس','Contact phone','د اړیکې کس تلفن'],['ایمیل شخص تماس','Contact email','د اړیکې کس برېښنالیک'],['حذف شخص تماس','Remove contact person','د اړیکې کس لرې کول'],
 ['مشخصات تازه اسناد ثبت‌شده قبلی را تغییر نمی‌دهد.','Updating these details does not rewrite previously posted documents.','د دې معلوماتو تازه کول پخوا ثبت شوي سندونه نه بدلوي.'],
 ['مبنای نرخ','Price basis','د بیې بنسټ'],['نرخ عمومی','Catalog price','عمومي بیه'],
 ['این نرخ با قرارداد مؤثر مشتری مطابق است.','This rate matches an effective customer agreement.','دا بیه د پېرودونکي له نافذ قرارداد سره برابره ده.'],
 ['این نرخ با نرخ عمومی محصول مطابق است.','This rate matches the product catalog price.','دا بیه د توکي له عمومي بیې سره برابره ده.'],
 ['نرخ سفارش مرتبط را پیش از ثبت بررسی کنید.','Review the linked order rate before posting.','له ثبت مخکې د تړلي فرمایش بیه وګورئ.'],
 ['نرخ متفاوت؛ سفارش مرتبط یا صلاحیت تغییر نرخ هنگام ثبت بررسی می‌شود.','Different rate; the linked order or price-override authority is checked at posting.','بیه توپیر لري؛ تړلی فرمایش یا د بیې بدلولو اجازه د ثبت پر مهال کتل کېږي.'],
 ['مطابق قرارداد مشتری','Matches customer agreement','د پېرودونکي له قرارداد سره برابر'],['مطابق سفارش','Matches linked order','له تړلي فرمایش سره برابر'],['تغییر نرخ مجاز','Authorized price override','د بیې مجاز بدلون'],
 ['مدیریت شرایط تأمین‌کننده','Manage supplier terms','د عرضه کوونکي شرایط اداره کول'],
];
i18n.addResourceBundle('en','translation',Object.fromEntries(copy.map(([fa,en])=>[fa,en])),true,true);
i18n.addResourceBundle('ps','translation',Object.fromEntries(copy.map(([fa,,ps])=>[fa,ps])),true,true);
