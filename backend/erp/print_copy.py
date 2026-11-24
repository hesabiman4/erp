"""Print captions; user-entered names, notes and evidence are never translated."""
PS={
 'ثبت نهایی / Posted':'وروستی ثبت','مسوده / Draft':'مسوده','بدون ثبت فروش / Non-posting commercial document':'سوداګریز سند؛ پلور نه ثبتوي','مانده لغوشده / Remainder cancelled':'پاتې لغوه شوې',
 'این نرخ‌نامه پیش از ثبت نهایی لغو شده است؛ فروش، دریافت یا خروج موجودی ایجاد نشده است. / This quotation was cancelled before posting; no revenue, collection or stock delivery was recorded.':'دا نرخ پاڼه له وروستي ثبت مخکې لغوه شوې؛ پلور، پیسې یا د زېرمو سپارل نه دي ثبت شوي.',
 'مسوده - این سند هنوز ثبت نهایی نشده است. / DRAFT - this document has not been posted.':'مسوده - دا سند لا وروستی ثبت شوی نه دی.',
 'این سند به تنهایی فروش، دریافت پول یا خروج موجودی را ثبت نمی‌کند. / This document alone does not record revenue, payment or stock delivery.':'دا سند پخپله پلور، پیسې یا د زېرمو سپارل نه ثبتوي.',
 'مانده این سند لغو شده است. تحویل‌ها، بل‌ها و پرداخت‌های قبلی به قوت خود باقی است. / The remainder is cancelled; previous deliveries, invoices and payments remain effective.':'د دې سند پاتې لغوه شوې. پخواني سپارل، بلونه او ورکړې پر خپل حال پاتې دي.',
 'لغو فقط برای مانده اجرا‌نشده است. اسناد فروش، دریافت و تحویل قبلی به قوت خود باقی است. / Cancellation preserves previously posted deliveries, invoices and payments.':'لغوه کول یوازې د ناتکمیل پاتې لپاره دي. پخواني ثبت شوي پلور، رسیدونه او سپارل پر خپل حال پاتې دي.',
 'انتقال و تصفیه بین شعب همین تجارت، فروش به مشتری بیرونی نیست. / Same-business transfers and internal settlements are not external customer sales.':'د همدې سوداګرۍ د څانګو تر منځ لېږد او داخلي تصفیه بهرني پېرودونکي ته پلور نه دی.',
 'چاپ سند / Print':'سند چاپول','کاپی / COPY':'کاپي','تاریخ سند / Date':'د سند نېټه','واحد پول / Currency':'اسعار',
 'مشخصات کارمند / EMPLOYEE':'د کارکوونکي معلومات','مشخصات تأمین‌کننده / SUPPLIER':'د عرضه کوونکي معلومات','مشخصات مشتری / CUSTOMER':'د پېرودونکي معلومات',
 'موقعیت / Location':'ځای','گدام / Warehouse':'ګودام','سند مرجع / Source':'اصلي سند','روش پرداخت / Method':'د ورکړې ډول','شماره مرجع / Reference':'د مرجع شمېره',
 'شرح محصول / Description':'د توکي تشریح','مقدار / Quantity':'مقدار','نرخ / Rate':'بیه','مبلغ / Amount':'مبلغ','تخفیف / Discount':'تخفیف','تعداد بلوک / Blocks':'د بلاکونو شمېر',
 'ثبت‌های حسابداری / Journal entries':'حسابداري ثبتونه','شرح حساب / Account':'د حساب تشریح','بدهکار / Debit':'بدهکار','بستانکار / Credit':'بستانکار','جزئیات سند / Document details':'د سند جزییات',
 'تخصیص روی بل‌ها / Invoice allocations':'بلونو ته تخصیص','شماره بل / Invoice number':'د بل شمېره','تاریخ / Date':'نېټه','تخصیص / Applied':'تخصیص شوی',
 'مانده فعلی بل / Current balance':'د بل اوسنی پاتې','مانده فعلی / Current balance':'اوسنی پاتې','یادداشت / Notes':'یادښت','توضیح / Reason':'دلیل','زمان چاپ / Printed':'د چاپ وخت',
 'تهیه‌کننده / Prepared by':'چمتو کوونکی','دریافت‌کننده / Received by':'ترلاسه کوونکی','ثبت مربوط همین سند / Recorded under this document':'د همدې سند اړوند ثبت',
 'اقلام سند / Document items':'د سند توکي','محصولات تولیدشده / Production outputs':'تولید شوي توکي','مواد مصرف‌شده / Materials consumed':'مصرف شوي مواد',
 'تاریخ سررسید / Due date':'د ورکړې وروستۍ نېټه','مهلت پرداخت (روز) / Payment terms (days)':'د ورکړې موده (ورځې)',
 'معاش ناخالص / Gross earnings':'ناخالص معاش','کسورات / Deductions':'کسرونه','معاش خالص / Net earnings':'خالص معاش','دوره حسابداری / Accounting period':'حسابداري دوره',
 'ساعت تأییدشده / Approved hours':'تایید شوي ساعتونه','ماه قراردادی معاش / Contract earning month':'د معاش قراردادي میاشت','تقویم قرارداد / Contract calendar':'د قرارداد کلیزه',
 'روزهای ماه / Full contract period days':'د قرارداد د بشپړې دورې ورځې','روز تأییدشده / Approved days':'تایید شوې ورځې','کسر پیش‌پرداخت / Advance recovery':'د مخکینیو پیسو کسر',
 'باقی پیش‌پرداخت / Remaining advance':'پاتې مخکینۍ پیسې','معاش باقی / Remaining wages':'پاتې معاش','مانده پیش‌پرداخت / Advance balance':'د مخکینیو پیسو پاتې',
 'مانده تصفیه داخلی / Internal balance':'د داخلي تصفیې پاتې','آغاز دوره کار / Earning from':'د کار دورې پیل','پایان دوره کار / Earning through':'د کار دورې پای',
 'مبنای نرخ / Rate basis':'د بیې بنسټ','ارتفاع بلوک نهایی (mm) / Finished height':'د وروستي بلاک لوړوالی (mm)','سربلوک (mm) / Top trim':'د بلاک سر (mm)',
 'کف بلوک (mm) / Bottom trim':'د بلاک تل (mm)','ضایعات برش (mm) / Cutting loss':'د پرېکولو ضایعات (mm)','مقدار باقی انتقال / Transfer remaining':'د لېږد پاتې مقدار',
 'اعتبار باقی / Remaining credit':'پاتې اعتبار','نقد شمارش‌شده / Counted cash':'شمېرل شوې نغدې','مانده ثبت‌شده / Recorded balance':'ثبت شوی پاتې','تفاوت شمارش / Count variance':'د شمېرنې توپیر',
 'واحد پول ارزی / Foreign currency':'بهرني اسعار','مبلغ ارز / Foreign amount':'د اسعارو مبلغ','نقد معادل افغانی / Cash in AFN':'معادل افغانۍ نغدې','مانده ارزی / Remaining foreign amount':'د اسعارو پاتې',
 'نرخ تبدیل / Exchange rate':'د تبادلې بیه','سود / زیان اسعار / FX gain or loss':'د اسعارو ګټه یا زیان','ارز قراردادی / Invoice currency':'د بل اسعار',
 'مبلغ اصلی ارز / Original foreign amount':'د اسعارو اصلي مبلغ','مانده ارز قرارداد / Foreign balance':'د قرارداد د اسعارو پاتې','نرخ اولیه AFN / Original rate':'لومړنۍ بیه په افغانۍ',
 'دریافت نقدی / Cash received':'ترلاسه شوې نغدې','دریافت بانکی / Bank received':'په بانک کې ترلاسه شوې پیسې','مجموع اقلام / Subtotal':'د توکو مجموعه',
 'مالیه / Tax':'مالیه','مبلغ سند / Document total':'د سند مجموعه','نقد پرداخت‌شده هنگام ثبت / Cash paid at issue':'د ثبت پر مهال ورکړل شوې پیسې',
 'اعتبار پیش‌پرداخت هنگام ثبت / Credit at issue':'د ثبت پر مهال مخکینی اعتبار','سند لغو / Cancellation document':'د لغوه کولو سند','تاریخ لغو / Cancellation date':'د لغوه کولو نېټه',
 'دلیل لغو / Cancellation reason':'د لغوه کولو دلیل','مجموع تصفیه معاش / Total payroll settlement':'د معاش د تصفیې مجموعه','مبلغ این رسید / Receipt amount':'د دې رسید مبلغ',
 'رویدادهای تسویه این بل / Invoice settlement history':'د دې بل د تصفیې سابقه','شماره سند / Document number':'د سند شمېره','مجموع تخصیص تسویه / Total settlement allocations':'د تصفیې د تخصیص مجموعه',
 'نقد هنگام فروش / Cash at sale':'د پلور پر مهال نغدې','نقد / Cash':'نغدې','بانک / Bank':'بانک','ماهانه / Monthly':'میاشتنی','هفته‌وار / Weekly':'اوونیز',
 'روزانه / Daily':'ورځنی','ساعتی / Hourly':'ساعتنی','پروژه‌ای / Project':'پروژوي','هجری شمسی / Jalali':'هجري لمریز','میلادی / Gregorian':'میلادي',
 'ثبت‌شده / Posted':'ثبت شوی','پیش‌نویس / Draft':'مسوده','لغوشده / Cancelled':'لغوه شوی','نمونه / Preview':'بېلګه',
 'آدرس تحویل / Delivery address':'د سپارلو پته','شماره ثبت / Registration':'د ثبت شمېره',
 'ضخامت × تعداد ورق / Thickness × sheets':'ضخامت × د پاڼو شمېر','ابعاد روی بلوک / Block face':'د بلاک د مخ اندازه',
 'چاپ یا ذخیره به شکل PDF / Print or save as PDF':'چاپ یا د PDF په بڼه ساتل',
 'تولید، تجارت و حسابداری / Manufacturing & accounting':'تولید، سوداګري او حسابداري',
 'مبالغ این سند به واحد پول زیر است. / Document currency:':'د دې سند اسعار:',
 'مانده‌های فعلی شامل رویدادهای ثبت‌شده تا زمان چاپ است. / Current balances include posted activity through printing.':'اوسني پاتې د چاپ تر وخت ثبت شوي فعالیتونه رانغاړي.',
 'برای پیگیری حساب، شماره این سند را نگهداری کنید. / Keep this document number for account enquiries.':'د حساب د پوښتنو لپاره د دې سند شمېره وساتئ.',
 'نمای چاپ ساخته شد؛ چاپ فزیکی تأیید نشده است. / Print view generated; physical printing is not confirmed.':'د چاپ لید جوړ شو؛ فزیکي چاپ نه دی تایید شوی.',
}

TITLE_PS={'sale':'د پلور بل','quotation':'نرخ ورکول','sales_order':'د پلور فرمایش','purchase_order':'د پېرود فرمایش','purchase_bill':'د عرضه کوونکي بل','purchase_receive':'د توکو ترلاسه کولو رسید','receipt':'د پېرودونکي د پیسو رسید','supplier_payment':'عرضه کوونکي ته د ورکړې رسید','sales_return':'د پلور بېرته ستنولو اعتبار','purchase_return':'د پېرود بېرته ستنولو اعتبار','customer_refund':'پېرودونکي ته د پیسو بېرته ورکړه','supplier_refund':'د عرضه کوونکي د پیسو بېرته ترلاسه کول','payroll_accrue':'د معاش محاسبه','payroll_settle':'د معاش تصفیه','employee_advance':'کارکوونکي ته مخکینۍ پیسې','transfer_dispatch':'د زېرمو لېږد','transfer_receive':'د لېږد ترلاسه کول','expense_post':'د لګښت سند','production':'د تولید جوپه','production_complete':'د تولید بشپړول','trim':'د بلاک سمون','journal_adjust':'اصلاحي حسابداري سند'}

def caption(value,language='bilingual'):
    value=str(value or '')
    if language=='bilingual':return value
    if language=='ps':
        if value in PS:return PS[value]
        from .document_print import TITLES
        for kind,translated in TITLE_PS.items():
            if kind in TITLES and value==' / '.join(TITLES[kind]):return translated
        return value
    if ' / ' in value:
        fa,en=value.rsplit(' / ',1)
        return en if language=='en' else fa
    return value

def apply(view,options):
    lang=options['language'];template=options['template'];kind=view['doc'].kind
    view.update(print_profile=options['profile'],compact=options['compact'],print_language=lang,print_direction='ltr' if lang=='en' else 'rtl',print_lang_code={'en':'en','fa':'fa-AF','ps':'ps-AF','bilingual':'fa-AF'}[lang],print_margin=options['margin_mm'],print_family=options['family'])
    fa=template.get('title_dari') or view['title'];en=template.get('title_english') or view['english_title'];ps=template.get('title_pashto') or TITLE_PS.get(kind)
    view['title']=en if lang=='en' else ps if lang=='ps' and ps else fa
    view['english_title']=en if lang=='bilingual' or lang=='ps' and not ps else ''
    # Static missing advanced captions remain bilingual rather than invent a
    # translation of accounting/source terminology.
    captions=[label for label,_ in [*view.get('details',[]),*view.get('total_rows',[])]]+[view.get('status_label',''),view.get('notice','')]+[s['label'] for s in view.get('sections',[])]
    view['print_caption_fallback']=lang=='ps' and (not ps or any(' / ' in label and caption(label,'ps')==label for label in captions))
    return view
