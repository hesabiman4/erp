import i18n from './i18n';
const copy:[string,string,string][]=[
 ['مرکز کار','Work center','کاري مرکز'],['دقیقه','Minutes','دقیقې'],
 ['مرور اندازه‌های واقعی فابریکه','Measured factory review','د فابریکې د واقعي اندازو کتنه'],
 ['این مرور از ثبت واقعی همین دوره است؛ خروجی اولیه با موجودی قابل فروش فرق دارد. مصرف مواد و بهای تولید فقط با صلاحیت مربوط دیده می‌شود.','This review uses actual postings in this period; initial output differs from saleable stock. Material consumption and costs require their separate permissions.','دا کتنه د همدې مودې واقعي ثبتونه کاروي؛ لومړنی تولید له پلور وړ زېرمو توپیر لري. د موادو مصرف او لګښتونه جلا اجازه غواړي.'],
 ['بچ‌های مرحله‌ای آغازشده','Staged batches started','پیل شوې پړاویزې جوپې'],['ثبت‌های خروجی اندازه‌شده','Measured output postings','د اندازه شوي تولید ثبتونه'],
 ['خروجی اولیه به تفکیک محصول و اندازه','Initial output by product and footprint','لومړنی تولید د توکي او اندازې له مخې'],['تعداد بلوک تولیدشده','Blocks produced','تولید شوي بلاکونه'],
 ['ضایعات و سربلوک / کف بلوک اندازه‌شده','Measured trim and process loss','اندازه شوي د بلاک سر، تل او ضایعات'],
 ['درصد ضایعات فقط از ارتفاع‌های هم‌اندازه همین اصلاح بلوک محاسبه می‌شود؛ کیلوگرام مواد به سانتی‌متر تبدیل نمی‌شود.','Loss percentages compare full-face heights within the same trim profile; input kilograms are never converted to centimeters.','د ضایعاتو سلنه د بلاک د هماغې اندازې له لوړوالي حسابېږي؛ د موادو کیلوګرامونه سانتي مترو ته نه بدلېږي.'],
 ['ارتفاع اولیه (mm)','Initial height (mm)','لومړنی لوړوالی (mm)'],['ارتفاع محصول اصلی (mm)','Main output height (mm)','د اصلي تولید لوړوالی (mm)'],
 ['مصرف خالص واقعی مواد در دوره','Actual net material consumption in period','په موده کې د موادو واقعي خالص مصرف'],
 ['مصرف ثبت‌شده منهای برگشت مواد مصرف‌شده به انبار؛ صدور مواد به کف تولید به تنهایی مصرف نیست.','Recorded consumption less linked returns of consumed material; issuing stock to the factory floor alone is not consumption.','ثبت شوی مصرف منفي د مصرف شوو موادو بېرته ستنول؛ د تولید ځای ته د موادو لېږد پخپله مصرف نه دی.'],
 ['زمان ثبت‌شده کار و توقف تجهیزات','Recorded job time and equipment downtime','ثبت شوی کاري وخت او د تجهیزاتو درېدنه'],
 ['دقایق کارت کار، معاش یا درصد استفاده واقعی ماشین نیست. توقف فقط از تکمیل ترمیمات ثبت‌شده می‌آید.','Job-card minutes are not payroll or actual machine-utilization percentages. Downtime comes only from recorded maintenance completions.','د کاري کارت دقیقې معاش یا د ماشین د واقعي کارونې سلنه نه ده. درېدنه یوازې د ثبت شوو بشپړو ترمیماتو څخه راځي.'],
 ['زمان کارت‌های کار','Job-card time','د کاري کارتونو وخت'],['توقف ثبت‌شده ترمیمات','Recorded maintenance downtime','د ترمیماتو ثبت شوې درېدنه'],
 ['برای دیدن توقف تجهیزات، صلاحیت ترمیمات لازم است.','Maintenance access is required to view equipment downtime.','د تجهیزاتو د درېدنې لیدل د ترمیماتو اجازه غواړي.'],
 ['مصارف جذب‌شده و زیان غیرعادی','Absorbed costs and abnormal loss','جذب شوي لګښتونه او غیرعادي زیان'],
 ['این ارقام ثبت هزینه تازه نیست. مزد و سربار جذب‌شده قبلاً از اسناد مجاز به تولید انتقال یافته است.','These figures create no new expense. Absorbed labor and overhead were already transferred to production from eligible source documents.','دا شمېرې نوی لګښت نه ثبتوي. جذب شوي مزد او سربار مخکې له مجازو سندونو تولید ته لېږدول شوي.'],
 ['مزد جذب‌شده در تولید','Labor absorbed into production','په تولید کې جذب شوی مزد'],['سربار جذب‌شده در تولید','Overhead absorbed into production','په تولید کې جذب شوی سربار'],
 ['زیان غیرعادی ثبت‌شده','Recorded abnormal loss','ثبت شوی غیرعادي زیان'],
];
i18n.addResourceBundle('en','translation',Object.fromEntries(copy.map(([fa,en])=>[fa,en])),true,true);
i18n.addResourceBundle('ps','translation',Object.fromEntries(copy.map(([fa,,ps])=>[fa,ps])),true,true);
