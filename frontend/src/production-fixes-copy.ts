import i18n from './i18n';
const copy:Record<string,[string,string]>={
 'نام به دری':['Dari name','دري نوم'],
 'نام به انگلیسی':['English name','انګلیسي نوم'],
 'نام به پشتو':['Pashto name','پښتو نوم'],
 'بلوک در حال عمل‌آوری است؛ ارتفاع موجود تا تأیید کیفیت قابل فروش نیست.':['This block is curing; its physical height is not saleable until quality release.','بلوک د جوړېدو په پړاو کې دی؛ شته لوړوالی د کیفیت تر تایید پورې د پلور وړ نه دی.'],
 'بلوک تحت بررسی کیفیت است؛ پیش از فروش، آزادسازی مجاز لازم است.':['This block is on quality hold; authorized release is required before sale.','بلوک د کیفیت تر کتنې لاندې دی؛ له پلور مخکې اجازه لرونکی خوشې کول اړین دي.'],
 'ارتفاع قابل فروش':['Saleable height','د پلور وړ لوړوالی'],
};
for(const [language,index] of [['en',0],['ps',1]] as const)i18n.addResourceBundle(language,'translation',Object.fromEntries(Object.entries(copy).map(([key,value])=>[key,value[index]])),true,true);
