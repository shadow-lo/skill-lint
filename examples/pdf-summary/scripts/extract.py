"""Print the text of a PDF, page by page."""
import sys

from pypdf import PdfReader

for i, page in enumerate(PdfReader(sys.argv[1]).pages, start=1):
    print(f"--- page {i} ---")
    print(page.extract_text() or "")
