"""
Extracts text styling from PDFs using pdfminer.
"""

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from io import BytesIO
from pprint import pprint
from typing import BinaryIO, Iterator, Optional
from xml.dom import minidom
from xml.dom.minidom import Element, Text

from pdfminer.pdfcolor import PDFColorSpace
from pdfminer.pdfdevice import PDFTextSeq, TagExtractor
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import (
    PDFGraphicState,
    PDFPageInterpreter,
    PDFResourceManager,
    PDFStackT,
    PDFTextState,
)
from pdfminer.pdfpage import PDFPage
from pdfminer.psparser import PSLiteral

from src.util.pdf_utils import Heading, as_pdf_doc, extract_outline, get_pdf_info

logger = logging.getLogger(__name__)


@dataclass
class Styling:
    # The text with the style
    text: str

    # Page number where the styled text is located
    pageno: int
    # Nested parent headings where the styled text is located
    headings: list[Heading]
    # Other text before and after the styled text to help find the correct occurrence of the text
    wider_text: str

    # Style attributes
    bold: bool = False


def extract_stylings(pdf: BinaryIO | PDFDocument) -> list[Styling]:
    parser = OutlineAwarePdfParser(pdf, BemTagExtractor)
    extracted_texts = parser.flatten_xml(parser.extract_xml())

    stylings: list[Styling] = []
    for text_obj in extracted_texts:
        if text_obj.zone != PageZone.MAIN or text_obj.is_heading():
            continue

        wider_text = "".join([p.text for p in text_obj.phrases])
        logger.debug(text_obj, wider_text[:100])
        for _phrase in text_obj.phrases:
            if _phrase.bold:
                styling = Styling(
                    text=_phrase.text,
                    pageno=text_obj.pageno,
                    headings=text_obj.headings,
                    wider_text=wider_text,
                    bold=_phrase.bold,
                )
                stylings.append(styling)
    return stylings


class PageZone(Enum):
    HEADER = "HEADER"
    MAIN = "MAIN"
    FOOTER = "FOOTER"


@dataclass
class Phrase:
    "Phrase is a piece of text with optional styling. It is a part of a paragraph (ExtractedText)."
    text: str
    bold: bool = False


@dataclass
class ExtractedText:
    pageno: int
    zone: PageZone
    headings: list[Heading]
    parano: int
    phrases: list[Phrase]

    def is_heading(self) -> bool:
        return self.parano == 0

    def __str__(self) -> str:
        if self.is_heading() and self.headings:
            last_heading = f"{self.headings[-1].level}:{self.headings[-1].title}"
            return f"{self.pageno}.{self.parano} {last_heading}"
        elif self.zone == PageZone.MAIN:
            return f"  {self.pageno}.{self.parano} {self.zone}"
        else:
            return f"({self.pageno} {self.zone})"


@dataclass
class ParsingContext:
    # Used to find headings in the PDF
    heading_stack: list[Heading]

    # The headings for the current text
    parent_headings: list[Heading] = field(default_factory=list)

    # Current page number
    pageno: int = 0

    # Paragraph number of the current text starting from 1 after each heading
    # Paragraph number is 0 for headings
    parano: int = -1

    _zone: PageZone | None = None

    def is_next_heading(self, phrases: list[Phrase]) -> Heading | None:
        # If there are no headings left, it's not a heading
        if not self.heading_stack:
            return None

        # Headings are expected to be the only text on the line or in a paragraph
        if len(phrases) != 1:
            return None

        # Headings are almost always bold
        phrase = phrases[0]
        if not phrase.bold:
            return None

        # Page number should match that of the headings from the PDF outline
        next_heading = self.heading_stack[-1]
        if next_heading.pageno != self.pageno:
            return None

        # Use casefold() to make case-insensitive comparison
        if phrase.text.strip().casefold() == next_heading.title.casefold():
            return next_heading

        return None

    def set_next_heading(self) -> None:
        next_heading = self.heading_stack.pop()
        level = next_heading.level

        # Update the parent_headings list with the new heading
        if level > len(self.parent_headings):  # new subheading
            self.parent_headings.append(next_heading)
        else:
            # Pop all subheadings (if any) until we reach level
            while level < len(self.parent_headings):
                self.parent_headings.pop()

            # Then set the current heading
            self.parent_headings[-1] = next_heading
        assert level == len(self.parent_headings)

        # Reset the paragraph number
        self.parano = 0

    @contextmanager
    def zone_context(self, zone: PageZone) -> Iterator[None]:
        self._zone = zone
        yield
        self._zone = None

    def create_extracted_text(self, phrases: list[Phrase]) -> ExtractedText:
        assert self._zone, "zone is not set"
        return ExtractedText(
            pageno=self.pageno,
            zone=self._zone,
            headings=self.parent_headings.copy(),
            parano=self.parano,
            phrases=phrases,
        )


class OutlineAwarePdfParser:
    """
    PDF parser that extracts text from a PDF using the PDF's outline metadata
    and flattens the resulting XML into ExtractedText objects
    """

    def __init__(self, pdf: BinaryIO | PDFDocument, tag_extractor_class: type):
        self.tag_extractor_class = tag_extractor_class
        self.disable_caching: bool = False
        self.doc = as_pdf_doc(pdf)

        # Get the PDF outline containing headings.
        # We'll use it to find headings in the text as the PDF is processed.
        self.parsing_context = ParsingContext(list(reversed(extract_outline(self.doc))))

    # Adapted from pdfminer.high_level.py:extract_text_to_fp() used in pdf2txt.py
    def _create_interpreter(
        self, output_io: BytesIO, output_codec: str = "utf-8"
    ) -> PDFPageInterpreter:
        rsrcmgr = PDFResourceManager(caching=not self.disable_caching)
        pdf_device = self.tag_extractor_class(rsrcmgr, outfp=output_io, codec=output_codec)
        return PDFPageInterpreter(rsrcmgr, pdf_device)

    def extract_xml(self, validate_xml: bool = False) -> str:
        "Stage 1: Generate XML from the PDF using custom tag_extractor_class"
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
            minidom.parseString(xml_string)  # nosec

        return xml_string

    def flatten_xml(self, xml_string: str) -> list[ExtractedText]:
        "Stage 2: Flatten the extracted XML into ExtractedText"
        pdf_info = get_pdf_info(self.doc, count_pages=True)
        xml_doc = minidom.parseString(xml_string)  # nosec
        root = xml_doc.documentElement
        result: list[ExtractedText] = []
        try:
            for page_node in root.getElementsByTagName("page"):
                self.parsing_context.pageno = int(page_node.getAttribute("id")) + 1
                logger.info("Processing page %i", self.parsing_context.pageno)

                for page_elem in page_node.childNodes:
                    if isinstance(page_elem, Element):
                        # An Element represents an XML tag
                        if annotated_text := self._create_extracted_text(page_elem):
                            result.append(annotated_text)
                    elif isinstance(page_elem, Text):
                        # A Text represents text content of an XML tag
                        # When text is not wrapped in a <P> tag (eg, 210.pdf)
                        with self.parsing_context.zone_context(PageZone.MAIN):
                            if phrase := self._create_phrase(None, page_elem):
                                self.parsing_context.parano += 1
                                result.append(self.parsing_context.create_extracted_text([phrase]))

            # Check that we've found all headings from the PDF outline
            assert len(self.parsing_context.heading_stack) == 0, self.parsing_context.heading_stack
            # Check that we've reached the last page
            assert self.parsing_context.pageno == pdf_info.page_count
            return result
        except Exception as e:
            print("Error processing XML:", pdf_info.title)
            pprint(self.parsing_context)
            raise e

    def _create_extracted_text(self, elem: Element) -> ExtractedText | None:
        if elem.tagName == "Artifact":
            if elem.getAttribute("Type") == "/'Pagination'":
                subtype = elem.getAttribute("Subtype")
                if subtype == "/'Header'":
                    return self._extract_text_in_zone(elem, PageZone.HEADER)
                if subtype == "/'Footer'":
                    return self._extract_text_in_zone(elem, PageZone.FOOTER)

            logger.info("Ignoring Artifact: %s", elem.toxml())
            return None

        if elem.tagName == "P":
            self.parsing_context.parano += 1

        if elem.tagName in ["P", "BOLD", "Span"]:
            return self._extract_text_in_zone(elem, PageZone.MAIN)

        raise NotImplementedError(f"Unhandled top-level element: {elem.toxml()}")

    def _extract_text_in_zone(self, elem: Element, zone: PageZone) -> ExtractedText | None:
        "Create ExtractedTExt from top-level element on a page"
        with self.parsing_context.zone_context(zone):
            phrases: list[Phrase] = self._extract_phrases(elem)

            if zone == PageZone.MAIN:
                # Check for headings and update the parsing context
                if self.parsing_context.is_next_heading(phrases):
                    self.parsing_context.set_next_heading()

            return self.parsing_context.create_extracted_text(phrases)

    def _extract_phrases(self, elem: Element) -> list[Phrase]:
        "Extract Phrases from lower-level (non-top-level) elements"
        phrases: list[Phrase] = []
        for child_node in elem.childNodes:
            if isinstance(child_node, Element):
                # Recurse and flatten the XML structure
                phrases += self._extract_phrases(child_node)
            elif isinstance(child_node, Text):
                if phrase := self._create_phrase(elem, child_node):
                    phrases.append(phrase)
            else:
                raise NotImplementedError(
                    f"Unexpected elem: {type(child_node)}, {self.parsing_context}"
                )
        return phrases

    def _create_phrase(self, parent_node: Element | None, child: Text) -> Phrase | None:
        # Ignore whitespace
        if not (child.data.strip()):
            return None

        bolded = bool(parent_node and parent_node.tagName == "BOLD")
        return Phrase(text=child.data, bold=bolded)


class BemTagExtractor(TagExtractor):
    """
    This class will write XML to the specified outfp, and is customized for BEM PDF files:
    - detects bold text
    - addresses Span tags that are not closed properly

    Methods in this class are called by the PDFPageInterpreter as it reads the PDF.
    This class is adapted from pdfminer.pdfdevice.TagExtractor used by
        pdfminer.high_level.py:extract_text_to_fp(), which is used in pdf2txt.py.
    """

    def __init__(self, rsrcmgr: PDFResourceManager, outfp: BinaryIO, codec: str = "utf-8") -> None:
        super().__init__(rsrcmgr, outfp, codec)

        # Added the following in order to add the BOLD tag.
        # This reflects the last fontname used for a given tag level
        self._last_fontname_stack: list[str] = [""]

    def render_string(
        self,
        textstate: PDFTextState,
        seq: PDFTextSeq,
        ncs: PDFColorSpace,
        graphicstate: PDFGraphicState,
    ) -> None:
        "render_string() is called multiple times between each begin_tag() completion and before end_tag()"
        font = textstate.font
        assert font is not None

        last_fontname = self._last_fontname_stack[-1]
        if last_fontname != font.fontname:
            if "Bold" in font.fontname and (not last_fontname or "Bold" not in last_fontname):
                self._write("<BOLD>")
            elif "Bold" in last_fontname and "Bold" not in font.fontname:
                self._write("</BOLD>")
        self._last_fontname_stack[-1] = font.fontname

        # Following is copied from pdfminer.pdfdevice.TagExtractor.render_string()
        super().render_string(textstate, seq, ncs, graphicstate)

    def begin_tag(self, tag: PSLiteral, props: Optional[PDFStackT] = None) -> None:
        # Workaround for Span tags that are not closed properly
        # (i.e., BEM 101.pdf, 105.pdf, 203.pdf, 225.pdf, 400.pdf)
        if self._stack and self._stack[-1].name == "Span":
            self._stack.pop(-1)
            self._write("</Span>")

        self._last_fontname_stack.append("")

        super().begin_tag(tag, props)

    def end_tag(self) -> None:
        if "Bold" in self._last_fontname_stack[-1]:
            self._write("</BOLD>")

        self._last_fontname_stack.pop(-1)

        if not self._stack:
            logger.warning(
                "page %i: end_tag without matching begin_tag (ie, empty tag stack!); ignoring",
                self.pageno,
            )
            return

        super().end_tag()
