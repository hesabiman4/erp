"""ReportLab cover/page furniture and searchable handbook assembly.

The body uses native Chromium shaping for correct logical Dari text, complex
RTL tables and hyperlinks. ReportLab draws the vector cover and page furniture.
No database access or application mutation.
"""
import argparse,io,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.local/pdf-deps'))
from pypdf import PdfReader,PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor,white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import arabic_reshaper
from bidi.algorithm import get_display

P=argparse.ArgumentParser();P.add_argument('--map',type=Path);P.add_argument('--body',type=Path);P.add_argument('--metadata',type=Path,required=True);P.add_argument('--output',type=Path);args=P.parse_args()
meta=json.loads(args.metadata.read_text(encoding='utf8'));reader=PdfReader(args.map or args.body)
def walk(items):
    for item in items:
        if isinstance(item,list):yield from walk(item)
        else:yield item
destinations={}
for number,title in enumerate(meta['chapters'],1):
    target=reader.named_destinations.get('/chapter-'+str(number)) or reader.named_destinations.get('chapter-'+str(number))
    if target:destinations[title]=reader.get_destination_page_number(target)
missing=[name for name in meta['chapters'] if name not in destinations]
if missing:raise ValueError('Missing native chapter destinations: '+str(missing))
page_map={name:destinations[name]+2 for name in meta['chapters']}
if args.map:
    print(json.dumps(page_map,ensure_ascii=False));raise SystemExit(0)

W,H=A4;NAVY=HexColor('#142b43');TEAL=HexColor('#07858d');PALE=HexColor('#b9e3dd');INK=HexColor('#24394c');MUTED=HexColor('#587082')
pdfmetrics.registerFont(TTFont('NawaBody','C:/Windows/Fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('NawaBold','C:/Windows/Fonts/arialbd.ttf'))
def shaped(s):return get_display(arabic_reshaper.reshape(str(s)))
def rtl(c,s,x,y,size=12,bold=False,color=INK):
    c.setFont('NawaBold' if bold else 'NawaBody',size);c.setFillColor(color);c.drawRightString(x,y,shaped(s))
def fa(n):return str(n).translate(str.maketrans('0123456789','۰۱۲۳۴۵۶۷۸۹'))
edition_year,edition_month,edition_day=(int(part) for part in meta['edition'].split('-'))
afghan_months={1:'جنوری',2:'فبروری',3:'مارچ',4:'اپریل',5:'می',6:'جون',7:'جولای',8:'اگست',9:'سپتمبر',10:'اکتوبر',11:'نومبر',12:'دسمبر'}
edition_text=f"نسخه {fa(edition_day)} {afghan_months[edition_month]} {fa(edition_year)}"
cover=io.BytesIO();c=canvas.Canvas(cover,pagesize=A4);c.setFillColor(NAVY);c.rect(0,0,W,H,fill=1,stroke=0)
c.setFillColor(TEAL);c.rect(W-14*mm,0,14*mm,H,fill=1,stroke=0);c.setFillColor(PALE);c.setFont('NawaBold',10);c.drawString(18*mm,H-25*mm,'NAWA / MANUFACTURING & ACCOUNTING')
rtl(c,'راهنمای کامل',W-26*mm,H-64*mm,32,True,white);rtl(c,'کار با نوا',W-26*mm,H-82*mm,32,True,white)
rtl(c,'از ساختن کسب‌وکار تا تولید، فروش و ختم دوره',W-26*mm,H-103*mm,16,False,PALE)
rtl(c,'گام‌های واقعی برنامه با مثال‌های عددی و تصویرهای آموزشی',W-26*mm,H-117*mm,12,False,white)
rtl(c,'دری افغانستان | برای کاربران مبتدی و مسؤولان شرکت',W-26*mm,H-128*mm,12,False,white)
# Authored vector manufacturing motif, not a density/weight conversion.
x,y=25*mm,70*mm;c.setLineWidth(1.2);c.setStrokeColor(PALE);c.setFillColor(HexColor('#23465c'));c.rect(x,y,48*mm,44*mm,fill=1,stroke=1)
p=c.beginPath();p.moveTo(x,y+44*mm);p.lineTo(x+12*mm,y+54*mm);p.lineTo(x+60*mm,y+54*mm);p.lineTo(x+48*mm,y+44*mm);p.close();c.drawPath(p,fill=1,stroke=1)
p=c.beginPath();p.moveTo(x+48*mm,y);p.lineTo(x+60*mm,y+10*mm);p.lineTo(x+60*mm,y+54*mm);p.lineTo(x+48*mm,y+44*mm);p.close();c.drawPath(p,fill=1,stroke=1)
c.setFillColor(TEAL);c.rect(x,y+37*mm,48*mm,7*mm,fill=1,stroke=0);rtl(c,'اندازه واقعی',x+42*mm,y+23*mm,11,True,white);rtl(c,'بها و فروش جدا',x+42*mm,y+14*mm,10,False,PALE)
for yy,big,label in [(113,fa(28),'فصل از آغاز تا پایان'),(91,fa(meta['recipes']),'بخش کاربردی'),(69,fa(178),'عملیات در فهرست مرجع')]:
    c.setFillColor(HexColor('#23465c'));c.roundRect(108*mm,yy*mm,70*mm,18*mm,2*mm,fill=1,stroke=0);rtl(c,big,172*mm,(yy+8)*mm,18,True,white);rtl(c,label,158*mm,(yy+4)*mm,9,False,PALE)
rtl(c,edition_text,W-26*mm,35*mm,11,True,white)
rtl(c,'اطلاعات و نرخ‌های کتاب آموزشی‌اند؛ در تجارت فعال نمونه ثبت نکنید.',W-26*mm,25*mm,9,False,PALE)
c.setTitle(meta['title']);c.showPage();c.save();cover.seek(0)
writer=PdfWriter();writer.append(PdfReader(cover));writer.add_outline_item('جلد - '+meta['title'],0);writer.append(reader,import_outline=False)
writer.add_outline_item('فهرست و مسیر آموزش',1)
for title in meta['chapters']:writer.add_outline_item(title,page_map[title]-1)
total=len(writer.pages);starts=sorted((destinations[name]+1,name) for name in meta['chapters'])
for i,page in enumerate(writer.pages):
    if i==0:continue
    chapter='فهرست و مسیر آموزش'
    for start,name in starts:
        if start<=i:chapter=name
    stream=io.BytesIO();stamp=canvas.Canvas(stream,pagesize=A4)
    stamp.setStrokeColor(HexColor('#d5e2e9'));stamp.setLineWidth(.4);stamp.line(17*mm,H-16.5*mm,W-17*mm,H-16.5*mm)
    stamp.setFont('NawaBody',7.5);stamp.setFillColor(MUTED);stamp.drawString(17*mm,H-12*mm,'NAWA / PRACTICAL USER GUIDE')
    text=shaped(chapter)
    while pdfmetrics.stringWidth(text,'NawaBody',8)>106*mm:chapter=chapter[:-2];text=shaped(chapter+'...')
    rtl(stamp,chapter,W-17*mm,H-12*mm,8,False,MUTED)
    stamp.line(17*mm,16*mm,W-17*mm,16*mm);stamp.setFont('NawaBody',7.5);stamp.drawString(17*mm,11*mm,f"Afghan Dari | Training data | {meta['edition']}");rtl(stamp,f'صفحه {fa(i+1)} از {fa(total)}',W-17*mm,11*mm,8,False,MUTED)
    stamp.showPage();stamp.save();stream.seek(0);page.merge_page(PdfReader(stream).pages[0]);page.compress_content_streams()
writer.add_metadata({'/Title':meta['title'],'/Author':'Nawa ERP documentation','/Subject':'Step-by-step Afghan Dari ERP operating handbook','/Creator':'ReportLab and native RTL handbook renderer'})
from pypdf.generic import NameObject,TextStringObject
writer.root_object[NameObject('/Lang')]=TextStringObject('fa-AF')
args.output.parent.mkdir(parents=True,exist_ok=True);temp=args.output.with_suffix('.tmp.pdf')
writer.compress_identical_objects(remove_duplicates=True,remove_unreferenced=True)
with temp.open('wb') as f:writer.write(f)
temp.replace(args.output)
verified=PdfReader(args.output);assert len(verified.pages)==total
print(json.dumps({'output':str(args.output),'pages':total,'body_pages':len(reader.pages),'chapter_pages':page_map,'operations':178,'recipes':meta['recipes'],'figures':meta['figures'],'internal_navigation':True,'layout_review':'Pending final render inspection'},ensure_ascii=False))
