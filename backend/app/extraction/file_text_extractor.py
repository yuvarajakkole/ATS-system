"""
Turns an uploaded resume file (PDF or LaTeX .tex source) into plain text,
BEFORE it ever reaches extract_resume(). Nothing downstream needs to know
or care what format the resume arrived in - this is the only place format
matters.

Verify-before-trust note: pdfplumber and pylatexenc are real, actively
maintained packages and their core APIs used below (pdfplumber.open +
page.extract_text(); pylatexenc.latex2text.LatexNodes2Text) were smoke-
tested during this build. That said, PDF layouts and LaTeX preambles vary
a lot in the wild - if you hit a resume that extracts badly (columns
jumbled, missing bullets, a scanned/image-only PDF with no text layer at
all), that's a real limitation of text extraction in general, not
something to silently paper over. Both functions raise a clear
ExtractionError rather than returning empty/garbled text silently.
"""
import io
import re

import pdfplumber
from pylatexenc.latex2text import LatexNodes2Text

MAX_FILE_BYTES = 8 * 1024 * 1024  # 8MB - generous for a resume, guards against accidental huge uploads


class ExtractionError(Exception):
    pass


def extract_text_from_pdf(file_bytes: bytes) -> str:
    if len(file_bytes) > MAX_FILE_BYTES:
        raise ExtractionError("PDF is larger than 8MB - that's unusual for a resume, please check the file.")
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages_text = [page.extract_text() or "" for page in pdf.pages]
    except Exception as e:
        raise ExtractionError(f"Could not open this file as a PDF: {e}")

    text = "\n".join(pages_text).strip()
    if not text:
        raise ExtractionError(
            "No extractable text found in this PDF. It may be a scanned "
            "image with no text layer (needs OCR, which this tool doesn't "
            "do) - try exporting the resume as text-based PDF, or paste "
            "the resume text directly instead."
        )
    return _clean_whitespace(text)


def extract_text_from_tex(file_bytes: bytes) -> str:
    if len(file_bytes) > MAX_FILE_BYTES:
        raise ExtractionError("The .tex file is larger than 8MB - that's unusual for a resume, please check the file.")
    try:
        source = file_bytes.decode("utf-8", errors="replace")
        text = LatexNodes2Text().latex_to_text(source)
    except Exception as e:
        raise ExtractionError(f"Could not parse this .tex file: {e}")

    text = text.strip()
    if not text:
        raise ExtractionError("The .tex file parsed but produced no visible text - check the source compiles/renders content.")
    return _clean_whitespace(text)


def _clean_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_resume_text_from_upload(filename: str, file_bytes: bytes) -> str:
    """Dispatches on file extension. Raises ExtractionError for anything else."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    if lower.endswith(".tex"):
        return extract_text_from_tex(file_bytes)
    raise ExtractionError(f"Unsupported file type for '{filename}'. Upload a .pdf or .tex file.")
