import logging
import math
import re
import sys
from collections import OrderedDict
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Sequence

from pdfminer.high_level import extract_text
from smart_open import open as smart_open
from unstructured.documents.elements import Element
from unstructured.partition.pdf import partition_pdf

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Document
from src.ingester import Split, save_to_db
from src.ingestion.markdown_chunking import chunk_tree
from src.ingestion.markdown_tree import create_markdown_tree
from src.ingestion.pdf_elements import EnrichedText, TextType
from src.ingestion.pdf_postprocess import add_markdown, associate_stylings, group_texts
from src.ingestion.pdf_stylings import (
    BemTagExtractor,
    extract_stylings,
    OutlineAwarePdfParser,
    PageZone,
)
from src.util.bem_util import build_bem_document_name, extract_bem_number
from src.util.file_util import get_file_name
from src.util.ingest_utils import DefaultChunkingConfig, IngestConfig, process_and_ingest_sys_args
from src.util.pdf_utils import extract_outline, get_pdf_info, Heading
from src.util.string_utils import headings_as_markdown, split_list, split_paragraph

logger = logging.getLogger(__name__)

PAGE_COUNT_PATTERN = re.compile(r"^\d+\s+of\s+\d+$", re.IGNORECASE)
HEADER_DATE_PATTERN = re.compile(r"^\d{1,2}-\d{1,2}-\d{4}$")
HEADER_BULLETIN_PATTERN = re.compile(r"^[A-Z]{2,}\s+\d{4}-\d{3,}$")
FOOTER_BLOCK_PATTERNS = (
    re.compile(r"^BRIDGES (ELIGIBILITY|ADMINISTRATIVE) MANUAL$", re.IGNORECASE),
    re.compile(r"^MICHIGAN DEPARTMENT OF [A-Z ]+$", re.IGNORECASE),
    re.compile(r"^CHILD DEVELOPMENT AND CARE$", re.IGNORECASE),
)


@dataclass(frozen=True)
class BemPageSection:
    bem_number: str
    title: str
    page_number: int


def _get_bem_title(file: BinaryIO, file_path: str) -> str:
    pdf_info = get_pdf_info(file)
    pdf_title = pdf_info.title or file_path
    try:
        bem_num = extract_bem_number(file_path)
    except ValueError:
        bem_num = Path(file_path).stem.upper()
    return build_bem_document_name(bem_num, pdf_title)


def _load_pdf_bytes(file_path: str) -> bytes:
    with smart_open(file_path, "rb") as file:
        return file.read()


def _public_sources_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "documents" / "public_sources"


def _cache_public_source_pdf(pdf_bytes: bytes, prefix: str = "BEM") -> str:
    filename = f"{prefix.lower()}-mobile.pdf"
    output_dir = _public_sources_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    output_path.write_bytes(pdf_bytes)
    return filename


def _get_public_source_url(filename: str) -> str:
    return f"{app_config.resolved_public_source_base_url}/sources/{filename}"


def _extract_page_sections(pdf_bytes: bytes, prefix: str = "BEM") -> dict[int, BemPageSection]:
    page_texts = extract_text(BytesIO(pdf_bytes)).split("\x0c")
    sections: dict[int, BemPageSection] = {}

    for page_number, page_text in enumerate(page_texts, start=1):
        if section := _extract_page_section(page_text, page_number, prefix):
            sections[page_number] = section

    return sections


def _extract_page_section(page_text: str, page_number: int, prefix: str = "BEM") -> BemPageSection | None:
    lines = [re.sub(r"\s+", " ", line).strip() for line in page_text.splitlines()]
    nonempty = [line for line in lines if line]

    bem_line_index = next((i for i, line in enumerate(nonempty) if f"{prefix} " in line), None)
    if bem_line_index is None:
        return None

    bem_number = extract_bem_number(nonempty[bem_line_index], prefix)
    remaining_lines = nonempty[bem_line_index + 1 :]

    if remaining_lines and PAGE_COUNT_PATTERN.fullmatch(remaining_lines[0]):
        remaining_lines = remaining_lines[1:]

    title_lines: list[str] = []
    for line in remaining_lines:
        if HEADER_DATE_PATTERN.fullmatch(line):
            break
        if HEADER_BULLETIN_PATTERN.fullmatch(line):
            continue
        title_lines.append(line)

    if not title_lines:
        return None

    return BemPageSection(
        bem_number=bem_number,
        title=" ".join(title_lines),
        page_number=page_number,
    )


def _render_grouped_text_as_markdown(grouped_text: EnrichedText) -> str:
    headings = [heading.title for heading in grouped_text.headings]
    heading_markdown = headings_as_markdown(headings)
    if heading_markdown:
        return f"{heading_markdown}\n\n{grouped_text.text}"
    return grouped_text.text


def _create_splits_for_grouped_text(grouped_text: EnrichedText) -> list[Split]:
    markdown = _render_grouped_text_as_markdown(grouped_text)
    try:
        tree = create_markdown_tree(markdown)
        tree_chunks = chunk_tree(tree, DefaultChunkingConfig())
    except Exception as exc:
        logger.warning(
            "Falling back to simple chunk splitting for page %s headings %s: %s",
            grouped_text.page_number,
            [heading.title for heading in grouped_text.headings],
            exc,
        )
        return _create_simple_splits_for_grouped_text(grouped_text)

    splits: list[Split] = []
    for chunk in tree_chunks:
        split = Split(
            chunk.headings or [heading.title for heading in grouped_text.headings],
            chunk.markdown,
            chunk.context_str,
            chunk.embedding_str,
            page_number=grouped_text.page_number,
        )
        split.chunk_id = chunk.id
        split.data_ids = ", ".join(chunk.data_ids)
        splits.append(split)
    return splits


def _create_simple_splits_for_grouped_text(grouped_text: EnrichedText) -> list[Split]:
    headings = [heading.title for heading in grouped_text.headings]
    context_str = "\n".join(headings)
    text = grouped_text.text.strip()
    if not text:
        return []

    token_count = app_config.embedding_model.token_length(text)
    if token_count > app_config.embedding_model.max_seq_length:
        num_splits = math.ceil((token_count * 1.5) / app_config.embedding_model.max_seq_length)
        char_limit_per_split = max(1, math.ceil(len(text) / num_splits))
        if grouped_text.type == TextType.LIST:
            text_splits = split_list(text, char_limit_per_split)
        elif grouped_text.type == TextType.LIST_ITEM:
            text_splits = split_list(text, char_limit_per_split, has_intro_sentence=False)
        else:
            text_splits = split_paragraph(text, char_limit_per_split)
    else:
        text_splits = [text]

    return [
        Split(
            headings,
            split_text.strip(),
            context_str,
            page_number=grouped_text.page_number,
        )
        for split_text in text_splits
        if split_text.strip()
    ]


def _group_texts_by_document(
    grouped_texts: Sequence[EnrichedText],
    page_sections: dict[int, BemPageSection],
    config: IngestConfig,
    source_url: str,
    file_path: str,
    pdf_bytes: bytes,
    prefix: str = "BEM",
) -> Sequence[tuple[Document, Sequence[EnrichedText]]]:
    if not page_sections:
        document = Document(
            name=_get_bem_title(BytesIO(pdf_bytes), file_path),
            source=source_url,
            content="\n\n".join(_render_grouped_text_as_markdown(text) for text in grouped_texts),
            **config.doc_attribs,
        )
        return [(document, list(grouped_texts))]

    documents: OrderedDict[str, tuple[Document, list[EnrichedText]]] = OrderedDict()
    for grouped_text in grouped_texts:
        if grouped_text.page_number is None:
            logger.warning("Skipping text with no page number: %r", grouped_text.text[:120])
            continue

        page_section = page_sections.get(grouped_text.page_number)
        if not page_section:
            logger.warning(
                "Skipping text on page %s with no %s section metadata", grouped_text.page_number, prefix
            )
            continue

        if page_section.bem_number not in documents:
            documents[page_section.bem_number] = (
                Document(
                    name=build_bem_document_name(page_section.bem_number, page_section.title, prefix),
                    source=source_url,
                    content="",
                    **config.doc_attribs,
                ),
                [],
            )
        documents[page_section.bem_number][1].append(grouped_text)

    results: list[tuple[Document, Sequence[EnrichedText]]] = []
    for document, texts in documents.values():
        document.content = "\n\n".join(_render_grouped_text_as_markdown(text) for text in texts)
        results.append((document, texts))
    return results


def _create_all_splits(
    grouped_documents: Sequence[tuple[Document, Sequence[EnrichedText]]],
) -> Sequence[tuple[Document, Sequence[Split]]]:
    return [
        (document, [split for text in texts for split in _create_splits_for_grouped_text(text)])
        for document, texts in grouped_documents
    ]


def _ingest_bem_pdfs(
    db_session: db.Session,
    pdf_path: str,
    config: IngestConfig,
    *,
    skip_db: bool = False,
    resume: bool = False,
    prefix: str = "BEM",
) -> None:
    del resume  # Resume does not materially change single-file ingestion behavior.

    logger.info("Processing %s PDF: %s using %s", prefix, pdf_path, app_config.embedding_model)
    pdf_bytes = _load_pdf_bytes(pdf_path)
    source_filename = _cache_public_source_pdf(pdf_bytes, prefix)
    source_url = _get_public_source_url(source_filename)

    grouped_texts = _parse_pdf(pdf_bytes, get_file_name(pdf_path), prefix)
    page_sections = _extract_page_sections(pdf_bytes, prefix)
    grouped_documents = _group_texts_by_document(
        grouped_texts,
        page_sections,
        config,
        source_url,
        pdf_path,
        pdf_bytes,
        prefix,
    )
    all_splits = _create_all_splits(grouped_documents)

    logger.info(
        "Prepared %d %s documents and %d chunk splits from %s",
        len(all_splits),
        prefix,
        sum(len(splits) for _, splits in all_splits),
        pdf_path,
    )

    if skip_db:
        logger.info("Skipping DB writes for %s ingestion", prefix)
        return

    save_to_db(db_session, resume=False, all_splits=all_splits)


def _parse_pdf(pdf_bytes: bytes, file_path: str, prefix: str = "BEM") -> list[EnrichedText]:
    enriched_texts = _enrich_texts(pdf_bytes, prefix)
    try:
        stylings = extract_stylings(BytesIO(pdf_bytes))
        associate_stylings(enriched_texts, stylings)
    except Exception as exc:  # pragma: no cover - styling extraction is best-effort
        logger.warning("%s: Failed to extract and associate stylings: %s", file_path, exc)
    markdown_texts = add_markdown(enriched_texts)
    return group_texts(markdown_texts)


def _enrich_texts(pdf_bytes: bytes, prefix: str = "BEM") -> list[EnrichedText]:
    outline: list[Heading] = extract_outline(BytesIO(pdf_bytes))
    try:
        unstructured_elem_list = partition_pdf(file=BytesIO(pdf_bytes), strategy="fast")
    except Exception as exc:
        logger.warning("Falling back to pdfminer text extraction after partition_pdf failed: %s", exc)
        return _fallback_enrich_texts(pdf_bytes, outline, prefix)

    if not any(getattr(element, "text", "").strip() for element in unstructured_elem_list):
        logger.warning("partition_pdf returned no text; falling back to pdfminer text extraction")
        return _fallback_enrich_texts(pdf_bytes, outline, prefix)

    enrich_text_list = []
    current_headings: list[Heading] = []

    prev_element_was_empty_list_item = False

    for element in unstructured_elem_list:
        if element.category == "Footer" or element.category == "Header":
            continue

        if element.category == "UncategorizedText" and re.match(
            r"^\d{1,2}-\d{1,2}-\d{4}$", element.text
        ):
            continue

        if element.category == "Title":
            if next_heading := _next_heading(outline, element, current_headings):
                current_headings = next_heading
                continue

        if element.category == "ListItem" and not element.text:
            prev_element_was_empty_list_item = True
            continue
        if prev_element_was_empty_list_item:
            if element.category in ("NarrativeText", "UncategorizedText", "Title"):
                element.category = "ListItem"
            else:
                logger.warning(
                    "Empty list item not followed by NarrativeText, UncategorizedText, or Title; page %i",
                    element.metadata.page_number,
                )
            prev_element_was_empty_list_item = False

        if element.category in ["UncategorizedText", "Address"]:
            element.category = "NarrativeText"

        try:
            enrich_text_list.append(
                EnrichedText(
                    text=element.text,
                    type=TextType(element.category),
                    page_number=element.metadata.page_number,
                    headings=current_headings,
                    id=element.id,
                )
            )
        except ValueError:
            logger.warning(
                "%s is not an accepted TextType; page %i: '%s'",
                element.category,
                element.metadata.page_number,
                element.text,
            )
    return enrich_text_list


def _fallback_enrich_texts(pdf_bytes: bytes, outline: list[Heading], prefix: str = "BEM") -> list[EnrichedText]:
    try:
        parser = OutlineAwarePdfParser(BytesIO(pdf_bytes), BemTagExtractor)
        extracted_texts = parser.flatten_xml(parser.extract_xml())

        enrich_text_list: list[EnrichedText] = []
        for text_index, text_obj in enumerate(extracted_texts, start=1):
            if text_obj.zone != PageZone.MAIN or text_obj.is_heading():
                continue

            normalized_text = re.sub(
                r"\s+",
                " ",
                "".join(phrase.text for phrase in text_obj.phrases),
            ).strip()
            if not normalized_text:
                continue

            enrich_text_list.append(
                EnrichedText(
                    text=normalized_text,
                    type=_infer_fallback_text_type(
                        normalized_text, normalized_text.startswith("\u2022")
                    ),
                    page_number=text_obj.pageno,
                    headings=text_obj.headings,
                    id=f"fallback-structured-{text_index}",
                )
            )
        if enrich_text_list:
            return enrich_text_list
    except Exception as exc:
        logger.warning(
            "Structured pdfminer fallback failed; falling back to raw page text extraction: %s", exc
        )

    return _fallback_enrich_texts_from_page_text(pdf_bytes, outline, prefix)


def _fallback_enrich_texts_from_page_text(pdf_bytes: bytes, outline: list[Heading], prefix: str = "BEM") -> list[EnrichedText]:
    enrich_text_list: list[EnrichedText] = []
    current_headings: list[Heading] = []

    for page_number, page_text in enumerate(extract_text(BytesIO(pdf_bytes)).split("\x0c"), start=1):
        if not page_text.strip():
            continue

        pending_list_item = False
        raw_blocks = [block for block in re.split(r"\n\s*\n+", page_text) if block.strip()]
        for block_index, block in enumerate(raw_blocks, start=1):
            normalized_block = re.sub(r"\s+", " ", block).strip()
            if not normalized_block or _is_header_or_footer_block(normalized_block, prefix):
                continue

            if heading := _match_heading(outline, normalized_block, page_number):
                current_headings = _update_current_headings(current_headings, heading)
                pending_list_item = False
                continue

            if normalized_block.replace(" ", "") == "\u2022":
                pending_list_item = True
                continue

            text_type = _infer_fallback_text_type(normalized_block, pending_list_item)
            enrich_text_list.append(
                EnrichedText(
                    text=normalized_block,
                    type=text_type,
                    page_number=page_number,
                    headings=current_headings.copy(),
                    id=f"fallback-{page_number}-{block_index}",
                )
            )
            pending_list_item = False

    return enrich_text_list


def _is_header_or_footer_block(block: str, prefix: str = "BEM") -> bool:
    return (
        bool(PAGE_COUNT_PATTERN.fullmatch(block))
        or bool(HEADER_DATE_PATTERN.fullmatch(block))
        or bool(HEADER_BULLETIN_PATTERN.fullmatch(block))
        or bool(re.fullmatch(rf"{prefix}\s+\d+", block, flags=re.IGNORECASE))
        or any(pattern.fullmatch(block) for pattern in FOOTER_BLOCK_PATTERNS)
    )


def _infer_fallback_text_type(block: str, pending_list_item: bool) -> TextType:
    if pending_list_item or block.startswith("\u2022"):
        return TextType.LIST_ITEM

    if (
        len(block) <= 80
        and not any(punctuation in block for punctuation in [".", ":", ";"])
        and block[0].isalpha()
    ):
        return TextType.TITLE

    return TextType.NARRATIVE_TEXT


def _update_current_headings(current_headings: list[Heading], heading: Heading) -> list[Heading]:
    if heading.level == 1:
        return [heading]

    if not current_headings or heading.title != current_headings[-1].title:
        updated_headings = current_headings[: heading.level - 1]
        updated_headings.append(heading)
        return updated_headings

    return current_headings


def _match_heading(
    outline: list[Heading], heading_name: str, page_number: int | None
) -> Heading | None:
    for heading in outline:
        if heading.pageno == page_number:
            heading_words = [
                character
                for character in heading.title.casefold()
                if not character.isspace() and character != "-"
            ]
            element_words = [
                character
                for character in heading_name.casefold()
                if not character.isspace() and character != "-"
            ]
            if heading_words == element_words:
                return heading
    return None


def _next_heading(
    outline: list[Heading], element: Element, current_headings: list[Heading]
) -> list[Heading] | None:
    if heading := _match_heading(outline, element.text, element.metadata.page_number):
        current_headings = _update_current_headings(current_headings, heading)
    else:
        return None
    return current_headings


def main() -> None:
    default_config = IngestConfig(
        "bridges-eligibility-manual",
        "mixed",
        "Michigan",
        app_config.resolved_public_source_base_url,
        "bridges-eligibility-manual",
    )
    process_and_ingest_sys_args(sys.argv, logger, _ingest_bem_pdfs, default_config)
