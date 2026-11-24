import i18n from './i18n';
const copy:[string,string,string][]=[
 ['تکمیل شده','Fulfilled','بشپړ شوی'],['مانده سفارش','Order remainder','د فرمایش پاتې'],['ورق','sheet(s)','پاڼه'],
 ['محصول غیرفعال','Inactive product','غیرفعال توکی'],
 ['بررسی آمادگی سفارش و وعده تحویل','Check order readiness and delivery promises','د فرمایش چمتووالی او د سپارلو ژمنې کتل'],
 ['آمادگی سفارش','Order readiness','د فرمایش چمتووالی'],['آماده در همین انبار','Ready in this warehouse','په همدې ګودام کې چمتو'],
 ['کمبود موجودی مناسب','Compatible stock shortage','د مناسبو زېرمو کمښت'],['اندازه و ضخامت برش را مشخص کنید','Specify footprint and cutting thickness','اندازه او د پرېکولو ضخامت وټاکئ'],
 ['توقف کیفیت محصول','Product quality hold','د توکي د کیفیت بندیز'],['خدمت؛ نیازمند بررسی مسؤول','Service; responsible person must review','خدمت؛ مسؤول باید کتنه وکړي'],
 ['این بررسی رزرو یا فروش نیست. موجودی هنگام برش یا بل‌کردن دوباره بررسی می‌شود؛ تاریخ تولید به تنهایی تضمین تحویل نیست.','This check creates no reservation or sale. Stock is rechecked at cutting or invoicing; a production date alone does not guarantee delivery.','دا کتنه زېرمه کول یا پلور نه جوړوي. زېرمه د پرېکولو یا بل جوړولو پر مهال بیا کتل کېږي؛ یوازې د تولید نېټه د سپارلو تضمین نه دی.'],
 ['تمام اقلام آماده است','All items are ready','ټول توکي چمتو دي'],['موارد نیازمند بررسی دارد','Some items need review','ځینې توکي کتنې ته اړتیا لري'],
 ['قابل تهیه در این بررسی','Available in this check','په دې کتنه کې شته'],['کمبود','Shortage','کمښت'],
 ['در سفارش مشخص نشده','Not specified on the order','په فرمایش کې نه دی ټاکل شوی'],['ضخامت مورد نیاز هر ورق (mm)','Required sheet thickness (mm)','د هرې پاڼې اړین ضخامت (mm)'],
 ['ضایعات برش هر ورق (mm)','Cutting loss per sheet (mm)','د هرې پاڼې د پرېکولو ضایعات (mm)'],
 ['مانده باید با تعداد صحیح ورق سازگار باشد. قطعات کوچک برای ساختن یک ورق ضخیم به هم جمع نمی‌شوند.','The remainder must correspond to whole sheets. Small pieces cannot be joined to supply one thick sheet.','پاتې مقدار باید له بشپړو پاڼو سره برابر وي. کوچنۍ ټوټې د یوې غټې پاڼې لپاره نه یوځای کېږي.'],
 ['قبلاً برای همین سفارش برش شده','Already cut for this order','د همدې فرمایش لپاره مخکې پرې شوې'],
 ['تولید برنامه‌شده مرتبط','Linked scheduled production','تړلی پلان شوی تولید'],
 ['این تاریخ برنامه است؛ تأیید کیفیت، برش، بارگیری و تحویل باید جدا بررسی شود.','These are scheduled dates; quality release, cutting, loading and delivery need separate review.','دا پلان شوې نېټې دي؛ د کیفیت تایید، پرېکول، بارول او سپارل جلا کتنه غواړي.'],
 ['وعده‌های تحویل بررسی‌شده','Reviewed delivery promises','کتل شوې د سپارلو ژمنې'],
 ['وعده تازه سابقه قبلی را حذف نمی‌کند و موجودی را رزرو نمی‌کند.','A new promise preserves earlier history and does not reserve stock.','نوې ژمنه پخوانۍ سابقه ساتي او زېرمه نه خوندي کوي.'],
 ['آخرین وعده ثبت‌شده','Latest recorded promise','وروستۍ ثبت شوې ژمنه'],['وعده قبلی','Earlier promise','پخوانۍ ژمنه'],
 ['مبنای وعده','Promise basis','د ژمنې بنسټ'],['ثبت وعده تحویل','Record delivery promise','د سپارلو ژمنه ثبتول'],['تاریخ وعده تحویل','Promised delivery date','د ژمنه شوي سپارلو نېټه'],
 ['موجودی مناسب، برنامه تولید، کیفیت، برش و حمل را با مسؤول مربوط بررسی کنید.','Review compatible stock, production schedule, quality, cutting and transport with the responsible staff.','مناسبه زېرمه، د تولید پلان، کیفیت، پرېکول او لېږد له اړوندو مسؤولینو سره وګورئ.'],
 ['دلیل / توافق با مشتری','Reason / customer agreement','دلیل / له پېرودونکي سره توافق'],['صلاحیت ثبت وعده تحویل','Record reviewed delivery promises','کتل شوې د سپارلو ژمنې ثبتول'],
];
i18n.addResourceBundle('en','translation',Object.fromEntries(copy.map(([fa,en])=>[fa,en])),true,true);
i18n.addResourceBundle('ps','translation',Object.fromEntries(copy.map(([fa,,ps])=>[fa,ps])),true,true);
