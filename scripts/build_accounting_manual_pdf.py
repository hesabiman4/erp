"""Publish the complete Markdown guide as an illustrated, searchable PDF.

Run with Python having reportlab, pypdf, arabic-reshaper and python-bidi.
The desktop bundled runtime supplies the PDF tools; optional local additions
live in .local/pdf-deps. This script does not access the ERP database.
"""
from __future__ import annotations
import argparse,hashlib,html,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.local/pdf-deps'))
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT,TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate,PageTemplate,Frame,Paragraph,Spacer,PageBreak,Table,TableStyle,Flowable,KeepTogether,CondPageBreak
from reportlab.platypus.tableofcontents import TableOfContents
from pypdf import PdfReader

NAVY=colors.HexColor('#142B43');TEAL=colors.HexColor('#087F78');INK=colors.HexColor('#243C50')
MUTED=colors.HexColor('#5B7081');LINE=colors.HexColor('#D9E4EB');PALE=colors.HexColor('#EFF7F5');WHITE=colors.white
PAGE_W,PAGE_H=A4;MARGIN=43;WIDTH=PAGE_W-2*MARGIN
STYLES={}

def fonts(directory=None):
    candidates=[Path(directory)] if directory else [Path('C:/Windows/Fonts'),Path('/usr/share/fonts/truetype/dejavu')]
    for folder in candidates:
        regular=folder/'arial.ttf' if (folder/'arial.ttf').is_file() else folder/'DejaVuSans.ttf'
        bold=folder/'arialbd.ttf' if (folder/'arialbd.ttf').is_file() else folder/'DejaVuSans-Bold.ttf'
        if regular.is_file() and bold.is_file():break
    else:raise RuntimeError('Provide --font-dir containing arial.ttf/arialbd.ttf or DejaVuSans fonts.')
    pdfmetrics.registerFont(TTFont('Body',str(regular)));pdfmetrics.registerFont(TTFont('BodyBold',str(bold)))
    pdfmetrics.registerFontFamily('Body',normal='Body',bold='BodyBold',italic='Body',boldItalic='BodyBold')
    base=dict(fontName='Body',textColor=INK,allowWidows=0,allowOrphans=0,splitLongWords=1)
    for name,size,leading,extra in [
        ('body',9.5,14.5,dict(spaceAfter=9)),('small',8.5,12.5,dict(spaceAfter=6)),
        ('table',8.4,12.3,{}),('th',8.4,11.5,dict(fontName='BodyBold',textColor=WHITE)),
        ('h1',22,27,dict(fontName='BodyBold',textColor=NAVY,spaceAfter=15,keepWithNext=True)),
        ('h2',12.5,17,dict(fontName='BodyBold',textColor=TEAL,spaceBefore=15,spaceAfter=9,keepWithNext=True)),
        ('cardtitle',10,14,dict(fontName='BodyBold',textColor=NAVY)),('cardmeta',7.9,11.5,dict(textColor=MUTED)),
        ('diagram',10,15,dict(textColor=INK)),('caption',8.4,12,dict(textColor=MUTED,spaceAfter=12)),
    ]:
        values={**base,**extra};STYLES[name]=ParagraphStyle(name,fontSize=size,leading=leading,**values)

def clean(value):
    value=value.replace('\u2011','-').replace('\u2013','-').replace('\u2014','-').replace('\u00a0',' ')
    value=value.replace('operating/investing/financing/internal/rate-effect','operating / investing / financing / internal / rate-effect')
    # Correct a few joined English/currency words in the source without altering facts.
    value=re.sub(r'(?<=[a-z])(?=(?:USD|AFN|CASH|AR|WIP)\b)',' ',value)
    return value

def shaped(value):
    # Preserve left-to-right accounting codes while shaping individual Dari runs.
    return re.sub(r'[\u0600-\u06ff]+(?:[ /\u200c]+[\u0600-\u06ff]+)*',lambda m:get_display(arabic_reshaper.reshape(m.group())),value)

def markup(value):
    value=clean(value)
    tokens={}
    def link(m):
        key=f'LINKTOKEN{len(tokens)}END';tokens[key]=f'<link href="{html.escape(m.group(2),quote=True)}" color="#087F78">{html.escape(shaped(m.group(1)))}</link>';return key
    value=re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)',link,value)
    value=html.escape(shaped(value))
    value=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',value)
    value=re.sub(r'`([^`]+)`',r'<font color="#087F78">\1</font>',value)
    value=value.replace('\n','<br/>').replace('&lt;br/&gt;','<br/>')
    for key,item in tokens.items():value=value.replace(key,item)
    return value

def para(text,style='body'):return Paragraph(markup(text),STYLES[style])

class Diagram(Flowable):
    def __init__(self,kind,height=290):Flowable.__init__(self);self.kind=kind;self.width=WIDTH;self.height=height
    def draw(self):
        c=self.canv;w=self.width;h=self.height
        c.setFillColor(colors.HexColor('#F7FAFC'));c.setStrokeColor(LINE);c.roundRect(0,0,w,h,10,fill=1,stroke=1)
        def text(x,y,label,size=10,color=INK,bold=False):
            c.setFillColor(color);c.setFont('BodyBold' if bold else 'Body',size);c.drawString(x,y,shaped(clean(label)))
        def box(x,y,bw,bh,title,lines,accent=TEAL):
            c.setFillColor(WHITE);c.setStrokeColor(LINE);c.roundRect(x,y,bw,bh,7,fill=1,stroke=1)
            c.setFillColor(accent);c.roundRect(x,y+bh-5,bw,5,2,fill=1,stroke=0)
            text(x+12,y+bh-25,title,10.5,NAVY,True)
            for i,line in enumerate(lines):
                pieces=re.split(r'\s{2,}',line)
                text(x+12,y+bh-46-i*17,pieces[0],9)
                if len(pieces)>1:c.drawRightString(x+bw-12,y+bh-46-i*17,pieces[1])
        def arrow(x1,y1,x2,y2,color=TEAL):
            import math
            c.setStrokeColor(color);c.setFillColor(color);c.setLineWidth(1.5);c.line(x1,y1,x2,y2)
            angle=math.atan2(y2-y1,x2-x1);p=c.beginPath();p.moveTo(x2,y2)
            p.lineTo(x2-7*math.cos(angle-.45),y2-7*math.sin(angle-.45));p.lineTo(x2-7*math.cos(angle+.45),y2-7*math.sin(angle+.45));p.close();c.drawPath(p,fill=1,stroke=0)
        if self.kind=='equation':
            text(20,h-30,'THE ACCOUNTING EQUATION',10,TEAL,True)
            bw=(w-76)/3
            for i,(title,value,notes) in enumerate([('ASSETS','222,500 AFN',['Cash + inventory','What the business controls']),('LIABILITIES','20,000 AFN',['Supplier debt','What the business owes']),('EQUITY','202,500 AFN',['Capital + earned profit',"Owner's residual interest"])]):
                x=18+i*(bw+20);box(x,h-167,bw,117,title,[value,*notes])
            text(18+bw+6,h-113,'=',14,TEAL,True);text(38+2*bw+6,h-113,'+',14,TEAL,True)
            text(22,78,'For every posting: total debits = total credits.',11,NAVY,True)
            text(22,53,'Dr CASH 500 / Cr AR 500: cash rises; existing customer debt falls.',9)
            text(22,32,'A collection does not create a second sale.',9,TEAL,True)
        elif self.kind=='manufacturing':
            text(20,h-29,'FOLLOW COST, NOT THE SELLING PRICE',10,TEAL,True)
            bw=(w-76)/3
            for i,(title,lines) in enumerate([('RAW MATERIALS',['20,000 AFN consumed','Actual inputs, no secret BOM']),('WORK IN PROGRESS',['20,000 + 3,000 + 2,000','Total cost: 25,000 AFN']),('FINISHED GOODS',['100 cm block: 25,000 AFN','Illustrative cost: 250 / cm'])]):
                box(18+i*(bw+20),h-157,bw,103,title,lines)
                if i<2:arrow(18+(i+1)*bw+i*20+3,h-105,18+(i+1)*(bw+20)-3,h-105)
            box(18,27,220,101,'BACKED CONVERSION COST',['Factory labor: 3,000 AFN','Eligible overhead: 2,000 AFN','Sources are absorbed only once.'])
            box(w-238,27,220,101,'DELIVERED TO CUSTOMER',['Sell 10 cm: sales 5,000 AFN','Release cost: COGS 2,500 AFN','Remain: 90 cm / FG 22,500 AFN'])
            arrow(128,128,18+(bw+20)+bw/2,h-157)
            arrow(18+2*(bw+20)+bw/2,h-157,w-128,128)
            text(21,9,'One compatible footprint; kerf 0 in this teaching example. Grade "45kg" is a name.',8,MUTED)
        elif self.kind=='balance':
            text(20,h-28,'CHECK THE COMPLETE EXAMPLE',10,TEAL,True)
            box(18,56,220,h-106,'ASSETS',['Cash                         170,000','Raw materials                  30,000','Finished goods                 22,500','TOTAL                         222,500'])
            box(w-238,56,220,h-106,'LIABILITIES + EQUITY',['Supplier payable                20,000','Opening capital                200,000','Current profit                   2,500','TOTAL                          222,500'])
            text(w/2-5,h/2-12,'=',16,TEAL,True)
            text(21,28,'Profit: 5,000 sales - 2,500 cost = 2,500 AFN. Cash is a different measure.',9,TEAL,True)
        elif self.kind=='customer':
            text(20,h-28,'ONE INVOICE, TWO COLLECTIONS',10,TEAL,True)
            bw=(w-76)/3
            items=[('SELL / DELIVER',['Invoice: 5,000 AFN','Dr AR 5,000','Cr SALES 5,000']),('RECEIVE 3,500',['Dr CASH 3,500','Cr AR 3,500','Debt remains: 1,500']),('RECEIVE 1,500',['Dr CASH 1,500','Cr AR 1,500','Debt remains: 0'])]
            for i,(title,lines) in enumerate(items):
                box(18+i*(bw+20),70,bw,120,title,lines)
                if i<2:arrow(18+(i+1)*bw+i*20+3,132,18+(i+1)*(bw+20)-3,132)
            text(20,43,'Total SALES stays 5,000 AFN, even after all 5,000 AFN has been collected.',10,TEAL,True)
            text(20,23,'Both payments must reference the original invoice, including walk-in sales.',9)
        elif self.kind=='payroll':
            text(20,h-28,'TWO LEDGERS, TWO DIFFERENT BALANCES',10,TEAL,True)
            box(18,63,220,h-114,'PAYROLL: COMPANY OWES',['Earned net wages               10,000','Less cash/bank payment           6,000','Less advance recovery            2,000','WAGES STILL PAYABLE              2,000'])
            box(w-238,63,220,h-114,'ADVANCES: EMPLOYEE OWES',['Advance previously paid          3,500','Less recovery in payroll         2,000','ADVANCE STILL OUTSTANDING        1,500'])
            text(20,37,'The 2,000 AFN recovery reduces both accounts. No second cash payment.',9.5,TEAL,True)
            text(20,18,'Separate illustrative example: no deductions, net earnings 10,000 AFN.',8.5,MUTED)
        elif self.kind=='fx':
            text(20,h-28,'KEEP FOREIGN QUANTITY AND AFN VALUE SEPARATE',10,TEAL,True)
            bw=(w-76)/3
            for i,(title,lines) in enumerate([('REGISTER USD 100',['At 70 AFN / USD','Receivable: 7,000 AFN','No second revenue entry']),('REVALUE AT 72',['USD debt stays 100','Receivable: 7,200 AFN','Unrealized gain: 200']),('COLLECT USD 40',['At 73: cash 2,920 AFN','Debt released: 2,880 AFN','Realized gain: 40 AFN'])]):
                box(18+i*(bw+20),h-174,bw,120,title,lines)
                if i<2:arrow(18+(i+1)*bw+i*20+3,h-114,18+(i+1)*(bw+20)-3,h-114)
            text(20,62,'Remaining USD 60 carries 4,320 AFN. Collect at 71: cash 4,260; loss 60.',9.5)
            text(20,39,'Then AR is zero. Historical as-of reports keep their earlier balances.',9.5,TEAL,True)
            text(20,18,'Illustrative approved rates, not a live exchange quotation.',8.5,MUTED)

class ManualDoc(BaseDocTemplate):
    def __init__(self,path):
        super().__init__(str(path),pagesize=A4,leftMargin=MARGIN,rightMargin=MARGIN,topMargin=57,bottomMargin=49,title='Nawa - Beginner Accounting Manual',author='Nawa ERP',subject='Complete account and operation guide with manufacturing examples',pageCompression=1)
        self.chapter='BEGINNER ACCOUNTING MANUAL'
        self.addPageTemplates(PageTemplate(id='manual',frames=[Frame(MARGIN,49,WIDTH,PAGE_H-106,id='body',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)],onPageEnd=self.chrome))
    def beforeDocument(self):self.chapter='BEGINNER ACCOUNTING MANUAL';self.heading_page=0;self.page_heading=self.chapter
    def chrome(self,c,doc):
        if doc.page==1:return
        c.saveState();c.setStrokeColor(LINE);c.setLineWidth(.6);c.line(MARGIN,PAGE_H-38,PAGE_W-MARGIN,PAGE_H-38)
        c.setFont('BodyBold',7.5);c.setFillColor(TEAL);c.drawString(MARGIN,PAGE_H-28,'NAWA / ACCOUNTING GUIDE')
        c.setFont('Body',7.1);c.setFillColor(MUTED);c.drawRightString(PAGE_W-MARGIN,PAGE_H-28,(self.page_heading if self.heading_page==doc.page else self.chapter)[:69])
        c.line(MARGIN,36,PAGE_W-MARGIN,36);c.setFont('Body',7.3);c.drawString(MARGIN,23,'Illustrative AFN examples | Source edition 2026-11-22');c.drawRightString(PAGE_W-MARGIN,23,str(doc.page));c.restoreState()
    def afterFlowable(self,flowable):
        if getattr(flowable,'chapter_title',None):
            title=flowable.chapter_title;key=flowable.chapter_key;self.chapter=clean(title)
            if self.heading_page!=self.page:self.heading_page=self.page;self.page_heading=self.chapter
            self.canv.bookmarkPage(key);self.canv.addOutlineEntry(clean(title),key,level=0,closed=False)
            self.notify('TOCEntry',(0,html.escape(clean(title)),self.page,key))

class Cover(Flowable):
    def __init__(self):Flowable.__init__(self);self.width=WIDTH;self.height=PAGE_H-110
    def draw(self):
        c=self.canv;w=WIDTH;h=self.height
        c.setFillColor(NAVY);c.rect(-MARGIN,-80,PAGE_W,PAGE_H+100,fill=1,stroke=0)
        c.setFillColor(TEAL);c.rect(-MARGIN,h+49,PAGE_W,12,fill=1,stroke=0)
        c.setFillColor(colors.HexColor('#8ED9CE'));c.setFont('BodyBold',11);c.drawString(0,h-48,'NAWA / MANUFACTURING & ACCOUNTING')
        c.setFillColor(WHITE);c.setFont('BodyBold',38)
        for i,line in enumerate(['Your guide to','business accounts']):c.drawString(0,h-153-i*48,line)
        c.setFont('Body',17);c.drawString(0,h-263,'A beginner accounting manual')
        c.setFont('Body',18);c.drawRightString(w,h-306,shaped('راهنمای حساب‌ها برای مبتدیان'))
        c.setFont('Body',11);c.setFillColor(colors.HexColor('#C5D7E4'))
        for i,line in enumerate(['Understand every account. Follow every operation.','See how materials become stock, sales and profit.','Built around the realities of Afghan manufacturing.']):c.drawString(0,h-365-i*21,line)
        for i,(big,label) in enumerate([(str(ACCOUNT_COUNT),'default accounts'),(str(OPERATION_COUNT),'system operations'),('AFN','worked examples')]):
            x=i*(w/3);c.setFillColor(colors.HexColor('#203E56'));c.roundRect(x,109,w/3-12,77,7,fill=1,stroke=0)
            c.setFillColor(WHITE);c.setFont('BodyBold',23);c.drawString(x+14,153,big);c.setFont('Body',9);c.drawString(x+14,132,label)
        c.setFillColor(colors.HexColor('#C5D7E4'));c.setFont('Body',9);c.drawString(0,67,'Complete reference with illustrated learning pages')
        c.drawString(0,47,'Source edition: 22 November 2026')
        c.setFont('Body',8);c.drawString(0,13,'Training examples describe implemented workflows; they are not live business records.')

def normal_table(headers,rows):
    count=len(headers)
    widths=([.25,.75] if count==2 else [.22,.34,.44] if count==3 else [.19,.27,.27,.27] if count==4 else [1/count]*count)
    data=[[para(x,'th') for x in headers]]+[[para(x,'table') for x in row] for row in rows]
    table=Table(data,colWidths=[WIDTH*x for x in widths],repeatRows=1,hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,colors.HexColor('#F4F8FA')]),('LINEBELOW',(0,0),(-1,0),.6,TEAL),('LINEBELOW',(0,1),(-1,-1),.35,LINE)]))
    return [table,Spacer(1,13)]

def reference_card(title,meta,left_title,left,right_title,right):
    t=Table([[para(title,'cardtitle'),''],[para(meta,'cardmeta'),''],[para(f'**{left_title}**\n{left}','small'),para(f'**{right_title}**\n{right}','small')]],colWidths=[WIDTH*.46,WIDTH*.54],hAlign='LEFT')
    t.setStyle(TableStyle([('SPAN',(0,0),(-1,0)),('SPAN',(0,1),(-1,1)),('BACKGROUND',(0,0),(-1,1),PALE),('BOX',(0,0),(-1,-1),.5,LINE),('LINEBEFORE',(1,2),(1,2),.4,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,0),10),('BOTTOMPADDING',(0,0),(-1,0),1),('TOPPADDING',(0,1),(-1,1),1),('BOTTOMPADDING',(0,1),(-1,1),8),('TOPPADDING',(0,2),(-1,2),9),('BOTTOMPADDING',(0,2),(-1,2),7)]))
    return KeepTogether([t,Spacer(1,10)])

def build(source,target):
    global ACCOUNT_COUNT,OPERATION_COUNT
    content=source.read_text(encoding='utf-8');ACCOUNT_COUNT=len(re.findall(r'^\| \d{5} · `',content,re.M));OPERATION_COUNT=len(re.findall(r'^\| `[a-z_]+` \|',content,re.M))
    lines=content.splitlines();story=[Cover(),PageBreak()]
    story+=[para('How to use this manual','h1'),para('Start with chapters 1 and 2, then follow the manufacturing example in chapter 4. Use chapters 3 and 5 as a desk reference when you need to identify an account or operation.'),para('The complete source content is included. Dense account and operation tables are presented as readable reference cards. Illustrations are teaching aids; the written workflow rules and implementation limits still apply.'),para('Navigation','h2')]
    toc=TableOfContents();toc.levelStyles=[ParagraphStyle('toc',fontName='Body',fontSize=10,leading=16,textColor=INK,spaceBefore=10,leftIndent=0,firstLineIndent=0)];story+=[toc,Spacer(1,18),para('Amounts are illustrative AFN. A sponge grade such as "45kg" is a product name, not a density or weight conversion. Actual-consumption manufacturing does not require a secret formula.','small'),PageBreak()]
    chapter=0;account_codes=[];operation_codes=[];i=0
    while i<len(lines):
        line=lines[i].strip()
        if not line:i+=1;continue
        if line.startswith('# '):i+=1;continue
        if line.startswith('## '):
            chapter+=1
            if chapter>1 and chapter!=10:story.append(PageBreak())
            title=line[3:];heading=para(title,'h1');heading.chapter_title=title;heading.chapter_key=f'chapter-{chapter}';story.append(heading)
            diagrams={1:[('equation',300,'Figure 1. The balance-sheet equation and the two sides of every posting. Amounts tie to the complete manufacturing example in chapter 4.')],4:[('manufacturing',320,'Figure 2. Actual input costs flow through WIP into finished stock and then cost of sales. The complete 13-step example follows.')],6:[('customer',255,'Figure 4. A partial payment reduces an existing debt; it does not create another sale.'),('payroll',285,'Figure 5. Wages payable and employee advance debt are separate ledgers. This example is independent of the manufacturing cycle.')],8:[('fx',290,'Figure 6. Foreign debt quantities and AFN carrying amounts are tracked independently.')]}
            for kind,height,caption in diagrams.get(chapter,[]):story.append(KeepTogether([Diagram(kind,height),Spacer(1,7),para(caption,'caption')]))
            i+=1;continue
        if line.startswith('### '):
            # A heading preceding nested reference-card KeepTogether objects
            # needs room for its first card, not merely a heading-sized gap.
            if line.startswith('### Reviewed operating improvements'):story.append(CondPageBreak(170))
            story.append(para(line[4:],'h2'));i+=1;continue
        if line.startswith('|'):
            table_lines=[]
            while i<len(lines):
                candidate=lines[i].strip()
                if candidate.startswith('|'):table_lines.append(candidate);i+=1
                elif not candidate and i+1<len(lines) and lines[i+1].strip().startswith('|'):i+=1
                else:break
            parsed=[[cell.strip() for cell in row.strip('|').split('|')] for row in table_lines];headers=parsed[0];rows=[row for row in parsed[1:] if not all(re.fullmatch(r':?-+:?',cell.replace(' ','')) for cell in row)]
            if headers[0]=='Number / code':
                for row in rows:
                    code=re.search(r'`([^`]+)`',row[0]).group(1);account_codes.append(code)
                    parts=row[1].split(' · ',1);title=f'{row[0]}  |  {parts[0]}'
                    story.append(reference_card(title,parts[1] if len(parts)>1 else '', 'Meaning and location',row[2],'Posting example and route',row[3]))
            elif headers[0]=='Operation':
                for row in rows:
                    code=row[0].strip('`');operation_codes.append(code)
                    story.append(reference_card(row[0],row[1],'Accounts affected',row[2],'Example and limits',row[3]))
            elif headers[0]=='Step':
                for row in rows:story.append(reference_card(f'STEP {row[0]}  |  {row[1]}','Complete manufacturing cycle - illustrative AFN','Debit',row[2],'Credit / result',row[3]+'<br/>'+row[4]))
                story.append(KeepTogether([Diagram('balance',265),Spacer(1,7),para('Figure 3. The complete example balances at 222,500 AFN. Unsold stock remains an asset.','caption')]))
            else:story+=normal_table(headers,rows)
            continue
        if line.startswith('- ') or re.match(r'^\d+\. ',line):
            prefix='- ' if line.startswith('- ') else re.match(r'^\d+\. ',line).group()
            story.append(para(prefix+line[len(prefix):],'body'));i+=1;continue
        paragraph=[line];i+=1
        while i<len(lines) and lines[i].strip() and not re.match(r'^(#|\||- |\d+\. )',lines[i].strip()):paragraph.append(lines[i].strip());i+=1
        story.append(para(' '.join(paragraph)))
    assert chapter==11 and len(account_codes)==ACCOUNT_COUNT and len(operation_codes)==OPERATION_COUNT and len(set(account_codes))==ACCOUNT_COUNT and len(set(operation_codes))==OPERATION_COUNT,(chapter,len(account_codes),len(operation_codes))
    target.parent.mkdir(parents=True,exist_ok=True);doc=ManualDoc(target);doc.multiBuild(story)
    reader=PdfReader(str(target));text='\n'.join(page.extract_text() or '' for page in reader.pages)
    for code in account_codes+operation_codes:assert code in text,f'Missing searchable identifier: {code}'
    assert len(reader.outline)==11
    verification={'pdf':str(target),'pages':len(reader.pages),'chapters':chapter,'accounts':len(account_codes),'operations':len(operation_codes),'figures':6,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'searchable_identifiers_checked':True,'chapter_bookmarks':len(reader.outline)}
    path=ROOT/'.local/design/pdf-manual';path.mkdir(parents=True,exist_ok=True);(path/'verification.json').write_text(json.dumps(verification,indent=2),encoding='utf-8');print(json.dumps(verification))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=ROOT/'docs/CHART_OF_ACCOUNTS_BEGINNER_MANUAL.md');parser.add_argument('--output',type=Path,default=ROOT/'output/pdf/Nawa_Beginner_Accounting_Manual.pdf');parser.add_argument('--font-dir');args=parser.parse_args();fonts(args.font_dir);build(args.source,args.output)
