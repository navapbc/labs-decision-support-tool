import json
import logging
import re
import sys
from typing import Sequence

from smart_open import open as smart_open

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.util.ingest_utils import (
    add_embeddings,
    deconstruct_list,
    deconstruct_table,
    process_and_ingest_sys_args,
    reconstruct_list,
    reconstruct_table,
    tokenize,
)
from src.util.string_utils import remove_links, split_markdown_by_heading

logger = logging.getLogger(__name__)


def _ingest_edd_web(
    db_session: db.Session,
    json_filepath: str,
    doc_attribs: dict[str, str],
) -> None:
    with smart_open(json_filepath, "r", encoding="utf-8") as json_file:
        json_items = json.load(json_file)

    # First, split all json_items into chunks (fast) to debug any issues quickly
    all_chunks = _create_chunks(json_items, doc_attribs)
    logger.info(
        "Done splitting %d webpages into %d chunks",
        len(json_items),
        sum(len(chunks) for _, chunks, _ in all_chunks),
    )
    for document, chunks, splits in all_chunks:
        logger.info("Adding embeddings for %r", document.source)
        # Next, add embeddings to each chunk (slow)
        add_embeddings(chunks, [s.text_to_encode for s in splits])
        logger.info("Embedded webpage across %d chunks: %r", len(chunks), document.name)

        # Then, add to the database
        db_session.add(document)
        db_session.add_all(chunks)


class SplitWithContextText:

    def __init__(self, headings: Sequence[str], text: str, context_str: str):
        self.headings = headings
        self.text = text
        self.text_to_encode = f"{context_str}\n\n" + remove_links(text)
        self.token_count = len(tokenize(self.text_to_encode))

    def add_if_within_limit(self, paragraph: str, delimiter: str = "\n\n") -> bool:
        new_text_to_encode = f"{self.text_to_encode}{delimiter}{remove_links(paragraph)}"
        token_count = len(tokenize(new_text_to_encode))
        if token_count <= app_config.sentence_transformer.max_seq_length:
            self.text += f"{delimiter}{paragraph}"
            self.text_to_encode = new_text_to_encode
            self.token_count = token_count
            return True
        return False

    def exceeds_limit(self) -> bool:
        if self.token_count > app_config.sentence_transformer.max_seq_length:
            logger.warning("Text too long! %i tokens: %s", self.token_count, self.text_to_encode)
            return True
        return False


def _create_chunks(
    json_items: Sequence[dict[str, str]],
    doc_attribs: dict[str, str],
) -> Sequence[tuple[Document, Sequence[Chunk], Sequence[SplitWithContextText]]]:
    urls_processed: set[str] = set()
    result = []
    for item in json_items:
        if item["url"] in urls_processed:
            # Workaround for duplicate items from web scraping
            logger.warning("Skipping duplicate URL: %s", item["url"])
            continue

        name = item["title"]
        logger.info("Processing: %s (%s)", name, item["url"])
        urls_processed.add(item["url"])

        content = item.get("main_content", item.get("main_primary"))
        assert content, f"Item {name} has no main_content or main_primary"

        document = Document(name=name, content=content, source=item["url"], **doc_attribs)
        chunks, splits = _chunk_page(document, content)
        result.append((document, chunks, splits))
    return result


def _chunk_page(
    document: Document, content: str
) -> tuple[Sequence[Chunk], Sequence[SplitWithContextText]]:
    splits: list[SplitWithContextText] = []
    for headings, text in split_markdown_by_heading(f"# {document.name}\n\n" + content):
        # Start a new split for each heading
        section_splits = _split_heading_section(headings, text)
        splits.extend(section_splits)

    chunks = [
        Chunk(
            document=document,
            content=split.text,
            headings=split.headings,
            num_splits=len(splits),
            split_index=index,
            tokens=split.token_count,
        )
        for index, split in enumerate(splits)
    ]
    return chunks, splits


# MarkdownHeaderTextSplitter splits text by "\n" then calls aggregate_lines_to_chunks() to reaggregate
# paragraphs using "  \n", so "\n\n" is replaced by "  \n"
MarkdownHeaderTextSplitter_DELIMITER = "  \n"


def _split_heading_section(headings: Sequence[str], text: str) -> list[SplitWithContextText]:
    # Add headings to the context_str; other context can also be added
    context_str = "\n".join(headings)
    logger.debug("New heading: %s", headings)

    # Keep intro sentence/paragraph together with the subsequent list or table by
    # replacing the MarkdownHeaderTextSplitter_DELIMITER with "\n\n" so that they are not split
    text = re.sub(
        rf"{MarkdownHeaderTextSplitter_DELIMITER}^( *[\-\*\+] )",
        r"\n\n\1",
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        rf"{MarkdownHeaderTextSplitter_DELIMITER}^(\| )", r"\n\n\1", text, flags=re.MULTILINE
    )

    splits: list[SplitWithContextText] = []
    # Split content by MarkdownHeaderTextSplitter_DELIMITER, then gather into the largest chunks
    # that tokenize to less than the max_seq_length
    paragraphs = text.split(MarkdownHeaderTextSplitter_DELIMITER)
    # Start new split with the first paragraph
    _create_splits(headings, context_str, splits, paragraphs)

    if len(splits) == 1:
        logger.debug("Section fits in 1 chunk: %s", headings[-1])
    else:
        logger.info("Split %i has %i tokens", len(splits), splits[-1].token_count)
        logger.info("Partitioned section into %i splits", len(splits))
        logger.debug("\n".join([f"[Split {i}]: {s.text_to_encode}" for i, s in enumerate(splits)]))
    return splits


def _create_splits(
    headings: Sequence[str],
    context_str: str,
    splits: list[SplitWithContextText],
    paragraphs: Sequence[str],
    delimiter: str = "\n\n",
) -> None:
    splits.append(SplitWithContextText(headings, paragraphs[0], context_str))
    logger.debug("Paragraph0: %r", paragraphs[0])
    for paragraph in paragraphs[1:]:
        logger.debug("Paragraph: %r", paragraph)
        _split_large_text_block(headings, context_str, splits)

        if not paragraph:
            continue
        if splits[-1].add_if_within_limit(paragraph, delimiter):
            logger.debug("adding to Split %i => %i tokens", len(splits), splits[-1].token_count)
        else:
            logger.info("Split %i has %i tokens", len(splits), splits[-1].token_count)
            # Start new split since longer_split will exceed max_seq_length
            splits.append(SplitWithContextText(headings, paragraph, context_str))
    _split_large_text_block(headings, context_str, splits)

    for split in splits:
        assert (
            not split.exceeds_limit()
        ), f"token_count: {split.token_count} > {app_config.sentence_transformer.max_seq_length}"


def _split_large_text_block(
    headings: Sequence[str], context_str: str, splits: list[SplitWithContextText]
) -> None:
    split = splits[-1]
    context_token_count = len(tokenize(f"{context_str}\n\n"))
    token_limit = app_config.sentence_transformer.max_seq_length - context_token_count
    if split.exceeds_limit():
        # Try to detect list items in the text_block
        intro_sentence, list_items = deconstruct_list(split.text)
        if list_items:
            splits.pop()
            logger.info(
                "Split text_block into %i list items with intro: %r",
                len(list_items),
                intro_sentence,
            )
            chunk_texts = reconstruct_list(token_limit, intro_sentence, list_items)
            _create_splits(headings, context_str, splits, chunk_texts)
        elif "| --- |" in split.text:
            table_intro_sentence, table_header, table_items = deconstruct_table(split.text)
            splits.pop()
            logger.info(
                "Split text_block into %i table items with intro: %r",
                len(table_items),
                table_intro_sentence,
            )
            chunk_texts = reconstruct_table(
                token_limit, table_intro_sentence, table_header, table_items
            )
            _create_splits(headings, context_str, splits, chunk_texts)
        elif split.text.count("\n") > 2:
            # Split text_block into smaller text_blocks
            chunk_texts = split.text.split("\n")
            splits.pop()
            logger.info("Split text_block into %i smaller text_blocks", len(chunk_texts))
            _create_splits(headings, context_str, splits, chunk_texts, delimiter="\n")
        else:
            raise ValueError(
                f"Cannot split long ({split.token_count} tokens) text_block: {split.text}"
            )


def main() -> None:
    process_and_ingest_sys_args(sys.argv, logger, _ingest_edd_web)
