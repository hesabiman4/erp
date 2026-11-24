"""Authored training, separated from operational facts and posting authority."""
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from .models import GuideProgress,AuditEvent

# Each paragraph is educational content, never a recipe, legal assertion or
# fabricated business result. Completion is personal learning, not approval.
GUIDES=[
 {'id':'sales','permissions':['sales.view','sales.post','sales.collect'],'path':'/sales','title':'فروش و دریافت پول','en':'Sales and collections','ps':'پلور او پیسې ترلاسه کول','steps':[
  ('measure','اندازه را تأیید کنید','۲۲ میلی‌متر برابر ۲٫۲ سانتی‌متر است. در یک بلوک ۱۰۰۰ میلی‌متری با ضایعات صفر، ۹۷۸ میلی‌متر باقی می‌ماند. درجه ۴۵ نام محصول است، وزن نیست.','Check the measurement','22 mm is 2.2 cm. A 1,000 mm block leaves 978 mm with zero cutting loss. Grade 45 is a product label, not weight.'),
  ('price','قیمت و مقدار را بررسی کنید','با نرخ ۵۰۰ افغانی برای هر سانتی‌متر، یک ورق ۲۲ میلی‌متری ۱۱۰۰ افغانی می‌شود. ابعاد روی بلوک و تعداد ورق باید مطابق سفارش باشد.','Review price and quantity','At 500 AFN/cm, one 22 mm sheet totals 1,100 AFN. Confirm the block footprint and sheet count.'),
  ('collect','دریافت را به همان بل وصل کنید','بل ۵۰۰۰ و دریافت ۳۵۰۰ افغانی، ۱۵۰۰ افغانی مانده دارد. دریافت بعدی فروش تازه نیست؛ مانده همان بل را کاهش می‌دهد.','Collect against the same invoice','An invoice of 5,000 with 3,500 collected leaves 1,500. Later collection reduces that invoice debt without another sale.') ]},
 {'id':'production','permissions':['production.post','production.view'],'path':'/production','title':'ثبت تولید واقعی','en':'Actual production','ps':'د حقیقي تولید ثبت','steps':[
  ('inputs','مصرف واقعی را ثبت کنید','مواد صادرشده به کف تولید با مواد مصرف‌شده در بچ فرق دارد. فقط مقدار واقعاً مصرف‌شده و اسناد کار و سربار مجاز وارد بهای تولید می‌شود.','Record actual consumption','Material issued to the floor differs from batch consumption. Only actual consumed material and eligible backed conversion costs enter production cost.'),
  ('outputs','خروجی را اندازه کنید','تعداد بلوک، طول، عرض و ارتفاع واقعی را ثبت کنید. مقدار خروجی از کیلوگرام مواد یا نام درجه حدس زده نمی‌شود. در حالت مصرف واقعی، فرمول لازم نیست.','Measure output','Record block count and actual length, width and height. Never infer output from input kilograms or the grade name. Actual-consumption mode needs no recipe.'),
  ('trim','سربلوک و کف بلوک را جدا کنید','اصلاح بلوک، ضایعات و محصول جانبی باید مستند باشد. فروش سربلوک بعداً فقط موجودی سربلوک را کاهش می‌دهد.','Separate trims and waste','Document trimming, by-products and waste. A later top-trim sale reduces trim stock only.') ]},
 {'id':'warehouse','permissions':['inventory.view','transfers.post','transfers.receive','inventory.count_record'],'path':'/inventory','title':'انبار و انتقال شعبه','en':'Warehouse and transfers','ps':'ګودام او لېږدونه','steps':[
  ('pieces','موجودی قطعه را ببینید','سانتی‌مترها فقط برای درجه و ابعاد یکسان قابل جمع است. ده قطعه کوتاه را نمی‌توان یک ورق ضخیم فرض کرد. رزرو و قرنطین را بررسی کنید.','Check physical pieces','Aggregate height only within a grade and footprint. Ten short remnants do not become one thick sheet. Check reservations and quality holds.'),
  ('dispatch','ارسال را ثبت کنید','انتقال داخلی به کابل فروش شرکت نیست. در ارسال، موجودی مبدأ کم و موجودی در مسیر زیاد می‌شود؛ درآمد ایجاد نمی‌شود.','Record dispatch','An internal transfer to Kabul is not company sales. Dispatch moves carrying value from origin inventory to transit, without revenue.'),
  ('receive','دریافت واقعی را تأیید کنید','شعبه مقصد فقط مقدار واقعاً دریافت‌شده را تأیید کند. کمبود یا خرابی را با دلیل ثبت کنید؛ دوباره ارسال تازه نسازید.','Confirm actual receipt','The destination confirms actual quantities received. Record shortages or damage with evidence instead of inventing another dispatch.') ]},
 {'id':'purchasing','permissions':['purchases.view','purchases.post','purchases.pay','purchases.rfq'],'path':'/purchases','title':'خرید، رسید و بل تأمین‌کننده','en':'Purchasing, receipts and bills','ps':'پېرود، رسید او د عرضه کوونکي بل','steps':[
  ('offer','پیشنهادها را مقایسه کنید','نرخ، کرایه تخمینی، مدت تحویل و شرایط پرداخت را ببینید. انتخاب پیشنهاد فقط سفارش خرید می‌سازد؛ موجودی یا بدهی تازه ثبت نمی‌کند.','Compare offers','Compare prices, estimated freight, lead time and terms. Awarding an offer creates a purchase order, without stock or payable posting.'),
  ('receipt','رسید را از بل جدا کنید','رسید خرید ورود واقعی کالا است. بل بعدی باید به همان رسید مربوط باشد تا موجودی دو بار زیاد نشود.','Separate receipt and bill','A receipt records real goods arrival. Link a later supplier bill to that receipt so stock is not received twice.'),
  ('evidence','مدرک را بررسی کنید','عکس یا PDF فقط مدرک است. معلومات استخراج‌شده را با اصل سند تطبیق کنید. مسوده تا ثبت نهایی، پرداخت یا مصرف حسابداری نیست.','Review source evidence','A photo or PDF is evidence. Compare extracted fields with the original. A draft is not a payment or posted expense.') ]},
 {'id':'cash','permissions':['cash_shifts.open','cash_shifts.review','finance.post'],'path':'/operations?view=cashier','title':'مسئولیت و شمارش صندوق','en':'Cash custody and counts','ps':'د صندوق مسؤولیت او شمېرنه','steps':[
  ('open','مانده افتتاحی را بشمارید','صندوق به حساب نقدی مستقل انتخاب‌شده مربوط است. آغاز نوبت باید با دفتر برابر باشد؛ پول تازه ایجاد نمی‌کند.','Count opening cash','The drawer covers its selected AFN cash instrument. Opening count must equal its books and creates no new money.'),
  ('freeze','شمارش ختم نوبت را ثبت کنید','پس از شمارش، دریافت و پرداخت نقد تا بررسی مسؤول یا شمارش مجدد متوقف می‌شود. دلیل تفاوت را نگه دارید.','Count and freeze','Counting freezes cash posting until supervisor review or recount. Retain evidence for differences.'),
  ('review','تفاوت را با صلاحیت بررسی کنید','کسری تأییدشده: بدهکار مصرف و بستانکار صندوق. اضافه: بدهکار صندوق و بستانکار سایر عواید. بدهی کارمند خودکار ایجاد نمی‌شود.','Review discrepancies','Approved shortage: debit expense, credit CASH. Overage: debit CASH, credit other income. No employee debt is invented.') ]},
 {'id':'accounting','permissions':['accounting.view','accounting.post','finance.statements'],'path':'/accounting','title':'بررسی حساب‌ها و بانک','en':'Accounts and bank review','ps':'د حسابونو او بانک کتنه','steps':[
  ('distinguish','فروش، نقد و سود را جدا بدانید','فروش با تحویل و بل ثبت می‌شود؛ دریافت پول ممکن است بعداً باشد. سود، فروش منهای بهای فروش و مصارف است.','Distinguish sales, cash and profit','Sales follow delivery/invoicing; cash may arrive later. Profit is revenue less cost of sales and expenses.'),
  ('bank','صورت‌حساب را با ثبت اصلی تطبیق کنید','در فایل بانک، واریز مثبت و برداشت منفی است. کارمزد ثبت‌نشده باید از جریان مصرف ثبت شود؛ ورود فایل خودکار پول یا مصرف نمی‌سازد.','Match original bank entries','Bank deposits are positive and withdrawals negative. Post missing fees through the expense workflow; importing evidence creates no money or expense.'),
  ('close','مغایرت را پیش از ختم دوره حل کنید','تراز آزمایشی، موجودی با دفتر، بدهی‌ها و مدارک را بررسی کنید. تکمیل این درس، تأیید حسابدار یا قفل دوره نیست.','Resolve differences before closing','Review trial balance, inventory controls, debt and evidence. Finishing this lesson is not accountant approval or a period lock.') ]},
 {'id':'payroll','permissions':['payroll.view','payroll.post','payroll.manage'],'path':'/employees','title':'معاش و پیش‌معاش','en':'Payroll and advances','ps':'معاش او مخکینۍ پیسې','steps':[
  ('terms','قرارداد و کار تأییدشده را ببینید','ماهانه، هفته‌وار، روزانه، ساعتی و پروژه‌ای شرایط جدا دارد. تقویم نمایش به‌تنهایی دوره قرارداد را تغییر نمی‌دهد.','Check terms and approved work','Monthly, weekly, daily, hourly and project terms differ. Changing the display calendar does not change contract periods.'),
  ('advance','پیش‌معاش را از مصرف معاش جدا کنید','پیش‌معاش دارایی قابل دریافت از کارمند است؛ محاسبه معاش، مصرف و بدهی معاش را ثبت می‌کند.','Separate advances from salary expense','An advance is a receivable from the employee. Accrual records salary expense and salary payable.'),
  ('recover','باقی‌مانده را حفظ کنید','اگر معاش ۲۰۰۰۰ و پیش‌معاش ۲۵۰۰۰ باشد، با بازیافت مجاز ۲۰۰۰۰، هنوز ۵۰۰۰ پیش‌معاش باقی است؛ پرداخت منفی نسازید.','Carry forward remaining advances','With 20,000 earned and 25,000 advanced, authorized recovery of 20,000 leaves 5,000 in advances. Do not create a negative salary payment.') ]}
]


# Authored Pashto teaching copy is separate from step identifiers and saved
# progress. Language changes never change a lesson's permission or version.
PASHTO_STEPS = {
 'sales': {
  'measure': ('اندازه تایید کړئ', '۲۲ ملي متره له ۲٫۲ سانتي متره سره برابر دي. که د ۱۰۰۰ ملي مترو بلوک د پرېکولو ضایعات صفر وي، ۹۷۸ ملي متره پاتې کېږي. ۴۵ د محصول درجه او نوم دی، وزن نه دی.'),
  'price': ('بیه او مقدار وګورئ', 'د هر سانتي متر په ۵۰۰ افغانیو بیه، د ۲۲ ملي مترو یوه پاڼه ۱۱۰۰ افغانۍ کېږي. د بلوک اوږدوالی، پلنوالی او د پاڼو شمېر له فرمایش سره پرتله کړئ.'),
  'collect': ('پیسې له هماغه بل سره وتړئ', 'که بل ۵۰۰۰ او ترلاسه شوې پیسې ۳۵۰۰ افغانۍ وي، ۱۵۰۰ افغانۍ پاتې دي. وروسته ترلاسه شوې پیسې نوی پلور نه دی؛ د هماغه بل پور کموي.')
 },
 'production': {
  'inputs': ('حقیقي مصرف ثبت کړئ', 'د تولید ځای ته ورکړل شوي مواد د بچ له مصرف شویو موادو سره توپیر لري. یوازې په رښتیا مصرف شوي مواد او د اسنادو له مخې منل شوي د کار او سربار لګښتونه د تولید په لګښت کې شاملېږي.'),
  'outputs': ('تولید شوی محصول اندازه کړئ', 'د بلوکونو شمېر او حقیقي اوږدوالی، پلنوالی او لوړوالی ثبت کړئ. د موادو له کیلوګرامونو یا د درجې له نوم څخه د محصول مقدار مه اټکل کوئ. د حقیقي مصرف په حالت کې فورمول ته اړتیا نشته.'),
  'trim': ('د بلوک سر، تل او ضایعات بېل کړئ', 'د بلوک سمول، جانبي محصولات او ضایعات مستند کړئ. وروسته د بلوک د سر پلور یوازې د هماغه جانبي محصول زېرمه کموي؛ د اصلي بلوک زېرمه بیا نه کموي.')
 },
 'warehouse': {
  'pieces': ('حقیقي ټوټې وګورئ', 'لوړوالی یوازې د یوې درجې او یو شان اوږدوالي او پلنوالي لپاره جمع کړئ. لس لنډې پاتې ټوټې یوه ضخیمه پاڼه نه جوړوي. رزرو شوې او د کیفیت تر بند لاندې ټوټې وګورئ.'),
  'dispatch': ('لېږل ثبت کړئ', 'کابل ته د همدې شرکت داخلي لېږد د شرکت پلور نه دی. د لېږلو پر وخت، د مبدأ زېرمه کمېږي او په لاره کې زېرمه زیاتېږي. د موجودۍ دفتري ارزښت ساتل کېږي او عاید نه جوړېږي.'),
  'receive': ('حقیقي ترلاسه شوی مقدار تایید کړئ', 'د ترلاسه کوونکې څانګې کارکوونکی دې یوازې په رښتیا ترلاسه شوی مقدار تایید کړي. کموالی یا زیان له دلیل او سند سره ثبت کړئ؛ د هغه د پټولو لپاره نوی لېږد مه جوړوئ.')
 },
 'purchasing': {
  'offer': ('وړاندیزونه پرتله کړئ', 'بیې، اټکلي کرایه، د سپارلو وخت او د پیسو شرطونه وګورئ. د وړاندیز غوره کول یوازې د پېرود فرمایش جوړوي؛ زېرمه یا د عرضه کوونکي پور نه ثبتوي.'),
  'receipt': ('د توکو رسید له بل څخه بېل کړئ', 'د پېرود رسید د توکو حقیقي رارسېدل ثبتوي. وروسته د عرضه کوونکي بل له هماغه رسید سره وتړئ، څو زېرمه دوه ځله زیاته نه شي.'),
  'evidence': ('اصلي سند وګورئ', 'انځور یا PDF د ثبوت سند دی. راایستل شوي معلومات له اصلي سند سره پرتله کړئ. مسوده تر وروستي ثبت مخکې نه د پیسو ورکړه ده او نه ثبت شوی حسابداري لګښت.')
 },
 'cash': {
  'open': ('د پیل نغدې وشمېرئ', 'صندوق د خپلې ټاکل شوې نغدي وسیلې افغانۍ رانغاړي. د نوبت د پیل شمېرنه باید له دفتري پاتې شونو سره برابره وي؛ دا شمېرنه نوې پیسې نه جوړوي.'),
  'freeze': ('د نوبت د پای شمېرنه ثبت کړئ', 'د شمېرنې له ثبت وروسته، نغدي ورکړې او ترلاسه کول د مسؤول تر کتنې یا بیا شمېرنې پورې بندېږي. د توپیر دلیل او اسناد وساتئ.'),
  'review': ('توپیر په صلاحیت وڅېړئ', 'تایید شوی کموالی: لګښت بدهکار او صندوق بستانکار کېږي. زیاتوالی: صندوق بدهکار او نور عواید بستانکار کېږي. د کارکوونکي پر غاړه په خپله پور نه اچول کېږي.')
 },
 'accounting': {
  'distinguish': ('پلور، نغدې او ګټه بېل وپېژنئ', 'پلور د توکو له سپارلو او بل سره ثبتېږي؛ پیسې ښايي وروسته ترلاسه شي. ګټه له عوایدو څخه د پلور د لګښت او نورو لګښتونو تر منفي کولو وروسته پاتې اندازه ده.'),
  'bank': ('د بانک اصلي ثبتونه تطبیق کړئ', 'د بانک په فایل کې جمع شوې پیسې مثبتې او ایستل شوې پیسې منفي دي. نه ثبت شوی بانکي فیس د عادي لګښت له لارې ثبت کړئ. یوازې د فایل راوړل پیسې یا لګښت نه جوړوي.'),
  'close': ('د دورې له تړلو مخکې توپیرونه حل کړئ', 'ازمایښتي بیلانس، له عمومي دفتر سره د زېرمې تطبیق، پورونه او اسناد وګورئ. د دې درس بشپړول د حسابدار تایید یا د مالي دورې قلف کول نه دي.')
 },
 'payroll': {
  'terms': ('شرطونه او تایید شوی کار وګورئ', 'میاشتني، اوونیز، ورځني، ساعتي او پروژوي قراردادونه بېل شرطونه لري. یوازې د ښودلو تقویم بدلول د قرارداد دوره نه بدلوي.'),
  'advance': ('مخکې ورکړل شوی معاش له لګښت څخه بېل کړئ', 'مخکې ورکړل شوې پیسې له کارکوونکي څخه د ترلاسه کولو شتمني ده. د معاش محاسبه د معاش لګښت او د ورکړې وړ معاش ثبتوي.'),
  'recover': ('پاتې مخکینۍ پیسې وساتئ', 'که ګټل شوی معاش ۲۰۰۰۰ او مخکې ورکړل شوې پیسې ۲۵۰۰۰ افغانۍ وي، د ۲۰۰۰۰ افغانیو له مجاز کسر وروسته لا هم ۵۰۰۰ افغانۍ مخکینۍ پیسې پاتې دي. منفي معاش مه ورکوئ.')
 }
}


def allowed_guides(ctx):
    return [g for g in GUIDES if any(ctx.has(p) for p in g['permissions'])]


def catalog(ctx):
    saved={p.topic:p for p in GuideProgress.objects.filter(business=ctx.business,membership=ctx.membership,version=1)}
    return [{**{k:v for k,v in g.items() if k!='permissions'},'steps_ps':{key:{'title':value[0],'body':value[1]} for key,value in PASHTO_STEPS[g['id']].items()},'version':1,'completed':saved[g['id']].completed if g['id'] in saved else []} for g in allowed_guides(ctx)]


@transaction.atomic
def save_progress(ctx,topic,completed):
    guide=next((g for g in allowed_guides(ctx) if g['id']==topic),None)
    if not guide:raise PermissionDenied('This learning topic is outside your permission scope.')
    if not isinstance(completed,list) or any(not isinstance(v,str) for v in completed) or len(completed)!=len(set(completed)) or not set(completed).issubset({s[0] for s in guide['steps']}):raise ValidationError('Select only the current lesson steps.')
    # Membership lock serializes concurrent progress without financial posting.
    type(ctx.membership).objects.select_for_update().get(pk=ctx.membership.pk)
    item,_=GuideProgress.objects.update_or_create(business=ctx.business,membership=ctx.membership,topic=topic,version=1,defaults={'completed':completed})
    AuditEvent.objects.create(business=ctx.business,user=ctx.user,action='learning.progress',target=str(item.pk),details={'topic':topic,'version':1,'completed':completed,'financial_effect':False})
    return {'topic':topic,'version':1,'completed':item.completed,'financial_effect':False}
