# Local receipt and supplier-bill capture

Open **Operations & planning → Receipt and bill capture** (`?view=capture`). The application extracts actual text locally from PNG, JPEG and PDF sources. It never uploads original documents to a cloud OCR service. The original bytes, SHA256, first-page image preview, extracted text, extraction method and human review remain private PostgreSQL evidence covered by encrypted database backups.

## Operating sequence

1. Select the actual location and upload a clear upright source. Limit:5 MB,16 million image pixels, one to five PDF pages and50,000 extracted characters. Password-protected PDFs and mismatched formats fail explicitly. Extraction runs in a bounded subprocess; unreadable sources require a new photograph or manual workflow.
2. Compare every original page. The workspace shows a first-page preview and provides the original download. Text-layer PDFs use local text extraction; image-only and mixed scanned PDFs use local OCR. Tesseract `eng+fas` recognizes English and Persian script; the `fas` model is not a certification of native Afghan Dari recognition accuracy.
3. Correct the proposed invoice date, amount and reference. Only unambiguous labelled totals and ISO Gregorian dates are suggested; unknown supplier, account and ambiguous dates stay blank. Supply the actual supplier and account/receipt yourself. Sources identifying foreign currency cannot be converted by this AFN flow; use the supported foreign workflow.
4. Explicitly confirm human review. An operating expense selects an ordinary non-control account, product line and actual CASH/BANK payment, or an unpaid supplier. A goods bill must match one complete original unbilled GRNI receipt, location, supplier and exact original total. Partial bills, prior returns and price changes use the existing ordinary controlled workflows.
5. The review creates **one ordinary draft**, with no cash, expense, liability or stock posting. Correct all fields before confirmation; approved capture fields are sealed against silent changes. Open the draft and use the ordinary final-post action. That action rechecks current permissions, open periods, real source quantities, approval limits and cash-shift controls, then uses the existing accounting service. Repeated posting cannot convert the captured source twice.
6. Reject unusable or unrelated evidence with a reason. The original remains preserved. This pilot does not implement re-review/amendment of a terminal capture review; do not confirm uncertain fields. A subsequent accounting error uses the normal documented reversal/correction workflow, preserving the original capture.

Exact source hashes cannot be imported twice within a business. Supplier references normalized for whitespace, case and local digits cannot create two reviewed capture drafts for the same supplier. Existing posted supplier references are also checked. These controls do not claim perceptual duplicate detection or guarantee detection of manually retyped transactions outside capture.

## Permissions and privacy

Source documents can contain confidential material, wages and financial details. Access therefore requires `capture.view`, `finance.view`, `cost.view`, `inventory.raw`, `payroll.view`, complete business location scope and full product scope. Upload additionally requires `capture.upload`; review/reject requires `capture.review`; draft creation/final posting retains `drafts.create` and the ordinary finance/purchasing permission. Existing staff receive no automatic new permission. Generic document JSON/print, original source and preview all recheck access. Ordinary source records do not expose source bytes or OCR text in their generic document data.

## Local engines and Python dependencies

Pinned Python packages: Pillow13.0.0 and pypdf6.21.4. The private Windows installation uses Tesseract5.4.0 (UB Mannheim distribution linked by the Tesseract project), English/Persian trained data, pypdf text extraction and Poppler rasterization. No system startup task or paid service is installed.

Defaults are `.local/tools/tesseract/tesseract.exe`, `.local/tools/tesseract/tessdata/{eng,fas}.traineddata`, and `.local/tools/poppler/Library/bin/pdftoppm.exe`. Server operators may configure `ERP_TESSERACT_PATH`, `ERP_TESSDATA_DIRECTORY`, `ERP_PDFTOPPM_PATH`; user-submitted paths and shell commands are never accepted. Linux operators install supported Tesseract/Poppler packages and configure the matching data directory. Missing configuration blocks import honestly. Native engines/language data need their own reviewed deployment packaging; the code checksum seal does not authenticate or package these private binaries.

Authoritative engine information: [Tesseract installation](https://tesseract-ocr.github.io/tessdoc/Installation.html), [Tesseract trained data](https://github.com/tesseract-ocr/tessdata_fast). Original recognizer output is untrusted evidence; real Afghan supplier documents, handwriting, rotated photos and representative bank exports need staff/native-editor acceptance. Handwriting, arbitrary layouts, automatic line-item matching, automatic tax determination and automatic posting are not supplied.

## Source map

`capture_models.py`, migration0029_document_capture, `capture.py`, `capture_extract.py`, `capture_api.py`, `document-capture.tsx`, `capture.css`, PostgreSQL tests in test_capture.py and an isolated QA browser journey in document-capture.spec.ts. Financial posting remains in core.execute/core.journal; upload/review/reject are nonfinancial evidence events.
