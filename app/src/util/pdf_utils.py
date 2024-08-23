from dataclasses import dataclass
from io import BufferedReader
from typing import Any

from pdfminer.pdfdocument import PDFDocument, PDFNoOutlines
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.pdftypes import PDFObjRef, resolve1
from pdfminer.psparser import PSLiteral


def as_pdf_doc(pdf: BufferedReader | PDFDocument):
    if isinstance(pdf, BufferedReader):
        doc = PDFDocument(PDFParser(pdf))
    else:
        doc = pdf
    return doc


def get_pdf_info(pdf: BufferedReader | PDFDocument) -> dict[str, Any]:
    doc = as_pdf_doc(pdf)
    assert len(doc.info) == 1
    doc_info = doc.info[0]
    return {
        "title": doc_info["Title"].decode(),
        "creation_date": doc_info["CreationDate"].decode(),
        "mod_date": doc_info["ModDate"].decode(),
        "producer": doc_info["Producer"].decode("utf16"),
        # "page_count": len(map_pages(doc)),
    }


def map_pages(doc: PDFDocument) -> dict[object, int]:
    return {page.pageid: pageno for (pageno, page) in enumerate(PDFPage.create_pages(doc), start=1)}


@dataclass
class Heading:
    title: str
    # Heading level starting from 1
    level: int
    # Page number where the heading first appears
    pageno: int | None = None


def extract_outline(pdf: BufferedReader | PDFDocument) -> list[Heading]:
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
