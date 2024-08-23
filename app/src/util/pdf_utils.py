from dataclasses import dataclass
from typing import Any

from pdfminer.pdfdocument import PDFDocument, PDFNoOutlines
from pdfminer.pdfpage import PDFPage
from pdfminer.pdftypes import PDFObjRef, resolve1
from pdfminer.psparser import PSLiteral


@dataclass
class Heading:
    title: str
    # Heading level starting from 1
    level: int
    # Page number where the heading first appears
    pageno: int | None


def extract_outline(doc: PDFDocument) -> list[Heading]:
    """
    Adapted from dumppdf.py:dumpoutline()
    Extracts the heading hierarchy from a PDF's catalog dictionary entry with key "Outlines".

    Usage:
        with open("100.pdf", "rb") as fp:
            doc = PDFDocument(PDFParser(fp))
            outline = extract_outline(doc)
    """

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

    pages = {
        page.pageid: pageno for (pageno, page) in enumerate(PDFPage.create_pages(doc), start=1)
    }
    outline = []
    try:
        outlines = doc.get_outlines()
        for level, title, dest, action, _se in outlines:
            pageno = None
            if dest:
                dest = resolve_dest(dest)
                pageno = pages[dest[0].objid]
            elif action and isinstance(action, dict):
                subtype = action.get("S")
                if subtype and repr(subtype) == "/'GoTo'" and action.get("D"):
                    dest = resolve_dest(action["D"])
                    pageno = pages[dest[0].objid]
            outline.append(Heading(title, level, pageno))
    except PDFNoOutlines:
        pass
    return outline
