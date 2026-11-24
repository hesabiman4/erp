"""Bounded local extraction subprocess. No Django, shell, network or remote OCR."""
import argparse,base64,io,json,os,subprocess
from pathlib import Path

MAX_TEXT=50000

def command(args,timeout=12):
    result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=False,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise ValueError('The local OCR/PDF engine could not read this file.')
    return result.stdout[:200000].decode('utf-8',errors='replace')

def ocr(path,args):
    return command([args.tesseract,str(path),'stdout','--tessdata-dir',args.tessdata,'-l','eng+fas','--psm','6'],20).strip()

def extract(args):
    from PIL import Image,ImageOps
    Image.MAX_IMAGE_PIXELS=16000000
    source=Path(args.input);pages=1
    if args.kind=='image':
        with Image.open(source) as image:
            if image.format not in {'PNG','JPEG'} or getattr(image,'n_frames',1)!=1:raise ValueError('Choose a single PNG or JPEG image.')
            image.verify()
        with Image.open(source) as image:
            if image.width*image.height>16000000:raise ValueError('Images are limited to16 million pixels.')
            target=source.with_suffix('.normalized.png');ImageOps.exif_transpose(image).convert('RGB').save(target)
        text=ocr(target,args);method='tesseract';preview=target
    else:
        from pypdf import PdfReader
        reader=PdfReader(source,strict=True)
        if reader.is_encrypted:raise ValueError('Password-protected PDFs are unsupported.')
        pages=len(reader.pages)
        if not 1<=pages<=5:raise ValueError('PDFs must contain one to five pages.')
        if any(float(page.mediabox.width)>2500 or float(page.mediabox.height)>2500 for page in reader.pages):raise ValueError('PDF page dimensions are too large.')
        page_text=[(page.extract_text() or '').strip() for page in reader.pages]
        text='\n\n'.join(page_text);method='pdf_text'
        if len(text)>MAX_TEXT:raise ValueError('PDF text exceeds the supported size.')
        # A mixed PDF still has to expose the scanned pages to the reviewer.
        # Raster every page if any page has no useful text, instead of silently
        # assuming the short text layer represents the entire uploaded invoice.
        if any(len(part)<20 for part in page_text):
            parts=[]
            for number in range(1,pages+1):
                prefix=source.parent/f'page-{number}'
                command([args.pdftoppm,'-f',str(number),'-l',str(number),'-scale-to','2400','-singlefile','-png',str(source),str(prefix)])
                parts.append(ocr(prefix.with_suffix('.png'),args))
            text='\n\n'.join(parts);method='pdf_tesseract'
        preview=source.parent/'page-1.png'
        if not preview.exists():command([args.pdftoppm,'-f','1','-l','1','-scale-to','1600','-singlefile','-png',str(source),str(preview.with_suffix(''))])
    if not text.strip():raise ValueError('No readable text was found. Retake a clear photograph or use manual entry.')
    if len(text)>MAX_TEXT:raise ValueError('Extracted text exceeds50,000 characters; split the document.')
    with Image.open(preview) as picture:
        picture=picture.convert('RGB');picture.thumbnail((1000,1400));buffer=io.BytesIO();picture.save(buffer,format='JPEG',quality=72)
    return {'text':text,'preview':base64.b64encode(buffer.getvalue()).decode('ascii'),'method':method,'pages':pages,'languages':['eng','fas'],'human_review_required':True}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);parser.add_argument('--kind',choices=['image','pdf'],required=True)
    for key in ['tesseract','tessdata','pdftoppm']:parser.add_argument('--'+key,required=True)
    args=parser.parse_args()
    try:result=extract(args)
    except Exception as error:
        result={'error':str(error) if isinstance(error,ValueError) else 'The source could not be safely extracted by the local engine.'}
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
