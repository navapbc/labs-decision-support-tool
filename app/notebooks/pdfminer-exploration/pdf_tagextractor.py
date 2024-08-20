# A good starting place to understand how pdfminer works is
# high_level.extract_text_to_fp() used by pdf2txt.py.
# Then test and examine the 2 possible PDFDevices:
# TagExtractor and HTMLConverter -- they output different semantic info.

# interpreter.process_page() calls device.end_page(), which calls device.receive_layout(LTPage)
# HTMLConverter recognizes bold via LTChar, whose fontname is set via device.render_char()
# but TagExtractor does not recognize bold b/c begin_tag(PSLiteral) doesn't have access to LTChar
#
# device.begin_tag(PSLiteral) is called by device.do_tag(PSLiteral) which is called by interpreter.do_BDC(PDFStackT)
# interpreter.do_* is called by main interpreter.execute(), which iterates through PSKeyword objects
# So: How are PSKeyword objects converted into LTChar objects?
#
# interpreter.process_page():
#     self.device.begin_page(page, ctm)
#     self.render_contents(page.resources, page.contents, ctm=ctm)
#        # calls interpreter.execute(), which calls device.do_tag() for TagExtractor
#     self.device.end_page(page)
#        # calls device.receive_layout(LTPage) for HTMLConverter
#
# font in device.render_char() is set via device.render_string() using PDFTextState.font
# AHA!: device.render_string(interpreter.textstate) is called by interpreter.do_TJ()
# So: Can use TagExtractor.render_string(PDFTextState)
# Need to use interpreter's self.textstate when interpreter.do_MP(PDFStackT) is called.
#
# do_Tf() sets textstate.font used by render_string()
# do_BT() calls self.textstate.reset()
# Tip: Add a printout in interpreter.execute() to see the order of PDF operators

import logging
from io import BytesIO
from pprint import pprint
from typing import Any, BinaryIO, List, Optional, cast
from xml.dom import minidom
from xml.dom.minidom import Element, Text

from pdfminer import utils
from pdfminer.pdfcolor import PDFColorSpace
from pdfminer.pdfdevice import PDFDevice, PDFTextSeq
from pdfminer.pdfdocument import PDFDocument, PDFNoOutlines
from pdfminer.pdffont import PDFUnicodeNotDefined
from pdfminer.pdfinterp import (
    PDFGraphicState,
    PDFPageInterpreter,
    PDFResourceManager,
    PDFStackT,
    PDFTextState,
)
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.pdftypes import PDFObjRef, resolve1
from pdfminer.psparser import PSLiteral
from pdfminer.utils import Matrix

from bem_extractions import AnnotatedText, Heading, PageInfo, ParsingContext

logger = logging.getLogger(__name__)


# Adapted from dumppdf.py:dumpoutline()
def extract_outline(doc: PDFDocument) -> List[Heading]:
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

    pages = map_pages(doc)
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


def map_pages(doc: PDFDocument) -> dict[object, int]:
    return {page.pageid: pageno for (pageno, page) in enumerate(PDFPage.create_pages(doc), start=1)}


def get_pdf_info(doc: PDFDocument) -> dict[str, Any]:
    assert len(doc.info) == 1
    doc_info = doc.info[0]
    return {
        "pdf": {
            # "filename": pdf_filename,
            "creation_date": doc_info["CreationDate"].decode(),
            "mod_date": doc_info["ModDate"].decode(),
            "producer": doc_info["Producer"].decode("utf16"),
            "page_count": len(map_pages(doc)),
        },
        "title": doc_info["Title"].decode(),
    }


class BemTagExtractor(PDFDevice):
    """
    Methods in this class are called by the PDFPageInterpreter as it reads the PDF.
    This class will write XML to the specified outfp.
    """

    def __init__(self, rsrcmgr: PDFResourceManager, outfp: BinaryIO, codec: str = "utf-8") -> None:
        PDFDevice.__init__(self, rsrcmgr)
        self.outfp = outfp
        self.codec = codec

        self.pageno = 0
        self._stack: List[PSLiteral] = []

        # Added the following in order to tag bold text.
        # This reflects the last fontname used for a given tag level
        self._last_fontname_stack: List[str] = [""]

    def render_string(
        self,
        textstate: PDFTextState,
        seq: PDFTextSeq,
        _ncs: PDFColorSpace,
        graphicstate: PDFGraphicState,
    ) -> None:
        """
        render_string() is called multiple times between each begin_tag() completion and before end_tag().
        """
        font = textstate.font
        assert font is not None
        print("render_string ", font, graphicstate.scolor, self._stack)

        color = None
        if isinstance(graphicstate.scolor, float):  # greyscale
            pass
        elif isinstance(graphicstate.scolor, tuple):
            if len(graphicstate.scolor) == 3:  # RGB
                color = str(graphicstate.scolor)
            elif len(graphicstate.scolor) == 4:  # CMYK
                pass

        last_fontname = self._last_fontname_stack[-1]
        if last_fontname != font.fontname:
            if "Bold" in font.fontname and (not last_fontname or "Bold" not in last_fontname):
                # print("<BOLD>", font.fontname)
                if color:
                    self._write(f'<BOLD color="{color}">')
                else:
                    self._write("<BOLD>")
            elif "Bold" in last_fontname and "Bold" not in font.fontname:
                # print("</BOLD>", font.fontname)
                self._write("</BOLD>")
        self._last_fontname_stack[-1] = font.fontname

        text = ""
        for obj in seq:
            if isinstance(obj, str):
                obj = utils.make_compat_bytes(obj)
            if not isinstance(obj, bytes):
                continue
            chars = font.decode(obj)
            for cid in chars:
                try:
                    char = font.to_unichr(cid)
                    text += char
                except PDFUnicodeNotDefined as e:
                    print("   !!! ", e)
                    pass
        print("text: ", text)
        self._write(utils.enc(text))

    def begin_tag(self, tag: PSLiteral, props: Optional[PDFStackT] = None) -> None:
        print("<<< begin_tag", tag, props, self._stack)

        # Don't allow nested Span tags
        # Workaround for Span tags that are not closed properly
        # (i.e., BEM 101.pdf, 105.pdf, 203.pdf, 225.pdf, 400.pdf)
        if self._stack and self._stack[-1].name == "Span":
            self._stack.pop(-1)
            self._write("</Span>")

        s = ""
        if isinstance(props, dict):
            s = "".join(
                [
                    f' {utils.enc(k)}="{utils.make_compat_str(v)}"'
                    for (k, v) in sorted(props.items())
                ]
            )
        out_s = f"<{utils.enc(cast(str, tag.name))}{s}>"
        self._write(out_s)
        self._stack.append(tag)
        self._last_fontname_stack.append("")
        return

    def end_tag(self) -> None:
        # Workaround: End bold tag if needed, even if `not self._stack` (e.g., BEM 210.pdf, 230A.pdf, 554.pdf)
        if "Bold" in self._last_fontname_stack[-1]:
            print("Workaround: </BOLD>")
            self._write("</BOLD>")
        self._last_fontname_stack.pop(-1)

        if not self._stack:
            print("!!! end_tag without matching begin_tag (i.e., empty tag stack!)", self.pageno)
            return
        assert self._stack, str(self.pageno)
        tag = self._stack.pop(-1)
        print(">>> end_tag", tag, self._stack)

        out_s = "</%s>" % utils.enc(cast(str, tag.name))
        self._write(out_s)
        return

    # do_*() methods refer to PDF Operators:
    # https://pdfa.org/wp-content/uploads/2023/08/PDF-Operators-CheatSheet.pdf
    def do_tag(self, tag: PSLiteral, props: Optional[PDFStackT] = None) -> None:
        self.begin_tag(tag, props)
        self._stack.pop(-1)
        return

    # cur_item: LTLayoutContainer
    def begin_page(self, page: PDFPage, ctm: Matrix) -> None:
        # print("======.... begin_page", page.pageid, self._stack)
        output = '<page id="%s" bbox="%s" rotate="%d">' % (
            self.pageno,
            utils.bbox2str(page.mediabox),
            page.rotate,
        )
        self._write(output)

        # (x0, y0, x1, y1) = page.mediabox
        # (x0, y0) = apply_matrix_pt(ctm, (x0, y0))
        # (x1, y1) = apply_matrix_pt(ctm, (x1, y1))
        # mediabox = (0, 0, abs(x0 - x1), abs(y0 - y1))
        # self.cur_item = LTPage(self.pageno, mediabox)
        return

    def end_page(self, page: PDFPage) -> None:
        assert not self._stack, str(len(self._stack))
        # assert isinstance(self.cur_item, LTPage), str(type(self.cur_item))
        # print("=====^^^^^^ end_page", page.pageid, self._stack)
        self._write("</page>\n")
        self.pageno += 1
        return

    def _write(self, s: str) -> None:
        self.outfp.write(s.encode(self.codec))


class BemPdfParser:
    def __init__(self, pdf_filename: str):
        self.disable_caching: bool = False

        self.fp = open(pdf_filename, "rb")
        self.doc = PDFDocument(PDFParser(self.fp))

        # Get the PDF outline containing headings.
        # We'll use it to find headings in the text as the PDF is processed.
        self.parsing_context = ParsingContext(list(reversed(extract_outline(self.doc))))

    def close(self) -> None:
        self.fp.close()

    # Adapted from pdfminer.high_level.py:extract_text_to_fp() used in pdf2txt.py
    def _create_interpreter(
        self, output_io: BytesIO, output_codec: str = "utf-8"
    ) -> PDFPageInterpreter:
        rsrcmgr = PDFResourceManager(caching=not self.disable_caching)
        # laparams: Optional[LAParams] = None
        # strip_control: bool = False

        # TODO: Extract images from the PDF:
        # output_dir = None
        # imagewriter = None
        # if output_dir:
        #     imagewriter = ImageWriter(output_dir)

        pdf_device = BemTagExtractor(rsrcmgr, outfp=output_io, codec=output_codec)
        return PDFPageInterpreter(rsrcmgr, pdf_device)

    # Stage 1: Generate XML from the PDF using custom BemTagExtractor
    def extract_xml(self, validate_xml: bool = False) -> str:
        output_io = BytesIO()
        interpreter = self._create_interpreter(output_io)
        for page in PDFPage.create_pages(self.doc):
            # As the interpreter reads the PDF, it will call methods on interpreter.device,
            # which will write to output_io
            interpreter.process_page(page)

        # After done writing to output_io, go back to the beginning so we can read() it
        output_io.seek(0)
        # Wrap all tags in a root tag
        xml_string = "<pdf>" + output_io.read().decode() + "</pdf>"

        if validate_xml:
            minidom.parseString(xml_string)

        return xml_string

    # Stage 2: Flatten the XML by page
    def to_annotated_texts(self, xml_string: str) -> list[object]:
        xml_doc = minidom.parseString(xml_string)
        root = xml_doc.documentElement

        doc_title = self.doc.info[0]["Title"].decode()
        result: list[object] = []
        try:
            for page_elem in root.getElementsByTagName("page"):
                self.parsing_context.page_info = PageInfo(
                    int(page_elem.getAttribute("id")) + 1, doc_title
                )
                print("Processing page", self.parsing_context.page_info.pageno)
                for child in page_elem.childNodes:
                    if child_tags := self._process_page_child(child):
                        result += child_tags

            # Check that we've found all headings from the PDF outline
            assert len(self.parsing_context.heading_stack) == 0
            # Check that we've reached the last page
            assert self.parsing_context.page_info.pageno == len(map_pages(self.doc))
        except Exception as e:
            print("Error processing XML:", get_pdf_info(self.doc))
            pprint(self.parsing_context)
            raise e

        return result

    TOP_HEADER = "TOP_HEADER"
    TEXT = "TEXT"

    def _process_page_child(self, child: Element) -> list[object] | None:
        match (child.nodeType):
            case child.ELEMENT_NODE:
                # print("--", child.tagName, child.nodeName)
                match (child.tagName):
                    case "Artifact":
                        # print(child.getAttribute("Type"), child.getAttribute("Subtype"))
                        if child.getAttribute("Subtype") == "/'Footer'":
                            # print("  (Ignoring Bottom_Footer)")
                            return None
                        return self.flatten_nodes(child, self.TOP_HEADER)
                    case "P":
                        return self.flatten_nodes(child, self.TEXT)
                    case "Span":
                        return self.flatten_nodes(child, self.TEXT)
                    case _:
                        print("!!! Unhandled: ", child.tagName)
            case _:
                print(f"(Ignoring: {child})")
        return None

    def flatten_nodes(self, node: Element, condition: str) -> list[object]:
        # print("flatten_nodes", node, condition)
        result: list[object] = []
        pc = self.parsing_context
        for child_node in node.childNodes:
            # print("type of child_node:", type(child_node))
            if isinstance(child_node, Element):
                # Recurse and flatten the XML structure by adding to result (rather than result.append())
                result += self.flatten_nodes(child_node, condition)
            elif isinstance(child_node, Text):
                child_text = child_node.data
                if not (stripped_text := child_text.strip()):
                    continue

                if condition == self.TOP_HEADER:
                    self.parsing_context.page_info.parse_header_item(stripped_text)
                elif condition == self.TEXT and pc.is_next_heading(stripped_text):
                    pc.set_next_heading()
                else:
                    pc.parano += 1

                    if node.tagName == "Span":
                        # TODO: capture hyperlink
                        pass

                    if node.tagName == "BOLD":
                        pc.tags[-1].append(stripped_text)

                    result.append(AnnotatedText(pc, node.tagName, child_text))
            else:
                print("!!! Unhandled: ", child_node)
        return result
