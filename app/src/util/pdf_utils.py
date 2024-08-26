from dataclasses import dataclass
from typing import Any, BinaryIO

from pdfminer.pdfdocument import PDFDocument, PDFNoOutlines
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.pdftypes import PDFObjRef, resolve1
from pdfminer.psparser import PSLiteral


def as_pdf_doc(pdf: BinaryIO | PDFDocument) -> PDFDocument:
    if isinstance(pdf, PDFDocument):
        return pdf
    else:
        return PDFDocument(PDFParser(pdf))


@dataclass
class PdfInfo:
    title: str | None = None
    creation_date: str | None = None
    mod_date: str | None = None
    producer: str | None = None
    page_count: int | None = None


def get_pdf_info(pdf: BinaryIO | PDFDocument, count_pages: bool = False) -> PdfInfo:
    doc = as_pdf_doc(pdf)
    assert len(doc.info) == 1, "Expected only 1 info dictionary in PDF document"
    doc_info = doc.info[0]
    pdf_info = PdfInfo()

    if "Title" in doc_info:
        pdf_info.title = doc_info["Title"].decode()

    if "CreationDate" in doc_info:
        pdf_info.creation_date = doc_info["CreationDate"].decode()

    if "ModDate" in doc_info:
        pdf_info.mod_date = doc_info["ModDate"].decode()

    if "Producer" in doc_info:
        pdf_info.producer = doc_info["Producer"].decode("utf16")

    if count_pages:
        pdf_info.page_count = len(map_pages(doc))

    return pdf_info


def map_pages(doc: PDFDocument) -> dict[object, int]:
    return {page.pageid: pageno for (pageno, page) in enumerate(PDFPage.create_pages(doc), start=1)}


@dataclass
class Heading:
    title: str
    # Heading level starting from 1
    level: int
    # Page number where the heading first appears
    pageno: int | None = None


def extract_outline(pdf: BinaryIO | PDFDocument) -> list[Heading]:
    """
    Adapted from dumppdf.py:dumpoutline()
    Extracts the heading hierarchy from a PDF's catalog dictionary entry with key "Outlines".

    Usage:
        with open("707.pdf", "rb") as fp:
            outline = extract_outline(fp)
    """
    doc = as_pdf_doc(pdf)
    pages = map_pages(doc)

    def resolve_dest(dest: object) -> Any:
        if isinstance(dest, (str, bytes)):
            dest = resolve1(doc.get_dest(dest))
        elif isinstance(dest, PSLiteral):
            dest = resolve1(doc.get_dest(dest.name))
        if isinstance(dest, dict):
            dest = dest["D"]
        if isinstance(dest, PDFObjRef):
            dest = dest.resolve()
        return dest

    def resolve_page_number(dest: Any, action: Any) -> int | None:
        if dest:
            dest = resolve_dest(dest)
            return pages[dest[0].objid]

        if action and isinstance(action, dict):
            subtype = action.get("S")
            if subtype and repr(subtype) == "/'GoTo'" and action.get("D"):
                dest = resolve_dest(action["D"])
                return pages[dest[0].objid]

        return None

    outline = []
    try:
        outlines = doc.get_outlines()
        for level, title, dest, action, _se in outlines:
            pageno = resolve_page_number(dest, action)
            outline.append(Heading(title, level, pageno))
    except PDFNoOutlines:
        pass
    return outline
