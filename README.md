<h1 align="center">KaramTC</h1>
<p align="center"><em>Karam Text Copier — copy text out of images and PDFs, fully offline</em></p>

**Image tab:** give it a JPEG, PNG, or WebP image and get the text back —
edit it, copy it, save it as a `.txt` file, or save it as a searchable PDF
(the original image with an invisible, selectable text layer positioned
exactly over it).

**PDF tab:** point it at a PDF and it extracts every page's text. Pages
with real selectable text are read directly (instant, perfect accuracy);
pages that are actually scanned images are converted and run through
Tesseract OCR — all in one pass. Output as a plain `.txt` file, a single
searchable PDF, or both. Extraction can be stopped and resumed later
without starting over, which matters for large scanned books.

**OCR Settings** (gear icon next to the language picker, shared by both
tabs): engine mode and page segmentation mode, custom Tesseract
parameters, and — no `sudo` needed — download Tesseract language data
directly in-app at one of three quality tiers (fast / standard / best),
independent from whatever your system package manager has installed.

Everything runs locally via [Tesseract](https://github.com/tesseract-ocr/tesseract)
and [PyMuPDF](https://github.com/pymupdf/PyMuPDF). No paid API, and no
internet connection required *unless* you use the in-app language
downloader — everything else works fully offline.

It runs on Linux and on Windows 10/11.

## License

AGPL-3.0-or-later — see [LICENSE](LICENSE).
