"""Structural PDF QA. Rendered-page visual inspection is a separate required step."""
import hashlib,json
from pathlib import Path
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[2]
folder=ROOT/'.local/production_guide_20261123'
build=json.loads((folder/'pdf-build.json').read_text())
pdf=Path(build['pdf']);reader=PdfReader(pdf)
assert len(reader.pages)==build['expected_pages']
assert all(len((page.extract_text() or '').strip())>25 for page in reader.pages)
images=sum(len(page.images) for page in reader.pages)
links=sum(len(page.get('/Annots',[])) for page in reader.pages)
assert images==build['screenshots']
assert links>=40
assert all(abs(float(page.mediabox.width)-841.92)<2 and abs(float(page.mediabox.height)-595.92)<2 for page in reader.pages)
assert reader.trailer['/Root'].get('/StructTreeRoot')
assert reader.trailer['/Root'].get('/Outlines')
report={'pages':len(reader.pages),'images':images,'links':links,'all_pages_have_text':True,'a4_landscape':True,'tagged':True,'outlines':True,'bytes':pdf.stat().st_size,'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest()}
(ROOT/'docs/production-guide/pdf-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
