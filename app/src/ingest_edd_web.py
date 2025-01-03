import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Callable, Optional, Sequence

from nutree import Tree
from smart_open import open as smart_open

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.ingestion.markdown_chunking import chunk_tree
from src.ingestion.markdown_tree import create_markdown_tree
from src.util.ingest_utils import (
    DefaultChunkingConfig,
    add_embeddings,
    deconstruct_list,
    deconstruct_table,
    document_exists,
    process_and_ingest_sys_args,
    reconstruct_list,
    reconstruct_table,
    tokenize,
)
from src.util.string_utils import remove_links, split_markdown_by_heading

logger = logging.getLogger(__name__)


class SplitWithContextText:

    def __init__(
        self,
        headings: Sequence[str],
        text: str,
        context_str: str,
        text_to_encode: Optional[str] = None,
    ):
        self.headings = headings
        self.text = text
        if text_to_encode:
            self.text_to_encode = text_to_encode
        else:
            self.text_to_encode = f"{context_str.strip()}\n\n" + remove_links(text)
        self.token_count = len(tokenize(self.text_to_encode))
        self.chunk_id = ""
        self.data_ids = ""

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


def _ingest_edd_web(
    db_session: db.Session,
    json_filepath: str,
    doc_attribs: dict[str, str],
    resume: bool = False,
) -> None:
    def prep_json_item(item: dict[str, str]) -> dict[str, str]:
        markdown = item.get("main_content", item.get("main_primary", None))
        assert markdown, f"Item {item['url']} has no main_content or main_primary"
        item["markdown"] = _fix_input_markdown(markdown)
        return item

    common_base_url = "https://edd.ca.gov/en/"
    ingest_json(db_session, json_filepath, doc_attribs, common_base_url, resume, prep_json_item)


def ingest_json(
    db_session: db.Session,
    json_filepath: str,
    doc_attribs: dict[str, str],
    common_base_url: str,
    resume: bool = False,
    prep_json_item: Callable[[dict[str, str]], dict[str, str]] = lambda x: x,
) -> None:
    json_items = load_json_items(db_session, json_filepath, doc_attribs, resume)

    for item in json_items:
        item = prep_json_item(item)

    # First, split all json_items into chunks (fast) to debug any issues quickly
    all_chunks = _create_chunks(json_items, doc_attribs, common_base_url)
    # Then save to DB, which is slow since embeddings are computed
    save_to_db(db_session, resume, all_chunks)


def load_json_items(
    db_session: db.Session, json_filepath: str, doc_attribs: dict[str, str], resume: bool = False
) -> Sequence[dict[str, str]]:
    with smart_open(json_filepath, "r", encoding="utf-8") as json_file:
        json_items = json.load(json_file)

    def verbose_document_exists(item: dict[str, str]) -> bool:
        if document_exists(db_session, item["url"], doc_attribs):
            logger.info("Skipping -- document already exists: %s", item["url"])
            return True
        return False

    if resume:
        json_items = [item for item in json_items if not verbose_document_exists(item)]

    return json_items


def save_to_db(
    db_session: db.Session,
    resume: bool,
    all_chunks: Sequence[tuple[Document, Sequence[Chunk], Sequence[SplitWithContextText]]],
) -> None:
    for document, chunks, splits in all_chunks:
        if not chunks:
            logger.warning("No chunks for %r", document.source)
            continue

        logger.info("Adding embeddings for %r", document.source)
        # Next, add embeddings to each chunk (slow)
        add_embeddings(chunks, [s.text_to_encode for s in splits])
        logger.info("Embedded webpage across %d chunks: %r", len(chunks), document.name)

        # Then, add to the database
        db_session.add(document)
        db_session.add_all(chunks)
        if resume:
            db_session.commit()


def _create_chunks(
    json_items: Sequence[dict[str, str]], doc_attribs: dict[str, str], common_base_url: str
) -> Sequence[tuple[Document, Sequence[Chunk], Sequence[SplitWithContextText]]]:
    urls_processed: set[str] = set()
    result = []
    for item in json_items:
        if item["url"] in urls_processed:
            # Workaround for duplicate items from web scraping
            logger.warning("Skipping duplicate URL: %s", item["url"])
            continue

        logger.info("Processing: %s", item["url"])
        urls_processed.add(item["url"])

        assert "markdown" in item, f"Item {item['url']} has no markdown content"
        content = item["markdown"]

        assert "title" in item, f"Item {item['url']} has no title"
        title = item["title"]
        document = Document(name=title, content=content, source=item["url"], **doc_attribs)
        if os.path.exists("SAVE_CHUNKS"):
            _save_markdown_to_file(document, common_base_url)
        chunks, splits = _chunk_page(document, common_base_url)
        logger.info("Split into %d chunks: %s", len(chunks), title)
        result.append((document, chunks, splits))
    logger.info(
        "Done splitting %d webpages into %d chunks",
        len(json_items),
        sum(len(chunks) for _, chunks, _ in result),
    )
    return result


USE_MARKDOWN_TREE = True


def _chunk_page(
    document: Document, common_base_url: str
) -> tuple[Sequence[Chunk], Sequence[SplitWithContextText]]:
    if USE_MARKDOWN_TREE:
        splits = _create_splits_using_markdown_tree(document, common_base_url)
    else:
        splits = []
        assert document.content
        for headings, text in split_markdown_by_heading(
            f"# {document.name}\n\n" + document.content
        ):
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


def _create_splits_using_markdown_tree(
    document: Document, common_base_url: str
) -> list[SplitWithContextText]:
    splits: list[SplitWithContextText] = []
    chunking_config = DefaultChunkingConfig()
    try:
        assert document.content
        tree = create_markdown_tree(
            document.content, doc_name=document.name, doc_source=document.source
        )
        tree_chunks = chunk_tree(tree, chunking_config)

        for chunk in tree_chunks:
            split = SplitWithContextText(
                chunk.headings, chunk.markdown, chunk.context_str, chunk.embedding_str
            )
            assert split.token_count == chunk.length
            splits.append(split)
            if os.path.exists("SAVE_CHUNKS"):
                # Add some extra info for debugging
                split.chunk_id = chunk.id
                split.data_ids = ", ".join(chunk.data_ids)
        if os.path.exists("SAVE_CHUNKS"):
            assert document.source
            path = "chunks-log/" + document.source.removeprefix(common_base_url).rstrip("/")
            _save_splits_to_files(f"{path}.json", document.source, document.content, splits, tree)
    except (Exception, KeyboardInterrupt) as e:  # pragma: no cover
        logger.error("Error chunking %s (%s): %s", document.name, document.source, e)
        logger.error(tree.format())
        raise e
    return splits


def _fix_input_markdown(markdown: str) -> str:
    # Fix ellipsis text that causes markdown parsing errors
    # '. . .' is parsed as sublists on the same line
    # in https://edd.ca.gov/en/uibdg/total_and_partial_unemployment_tpu_5/
    markdown = markdown.replace(". . .", "...")

    # Nested sublist '* + California's New Application' created without parent list
    # in https://edd.ca.gov/en/about_edd/eddnext
    markdown = markdown.replace("* + ", "    + ")

    # Blank sublist '* ###" in https://edd.ca.gov/en/unemployment/Employer_Information/
    # Tab labels are parsed into list items with headings; remove them
    markdown = re.sub(r"^\s*\* #+", "", markdown, flags=re.MULTILINE)

    # Blank sublist '* +" in https://edd.ca.gov/en/unemployment/Employer_Information/
    # Empty sublist '4. * ' in https://edd.ca.gov/en/about_edd/your-benefit-payment-options/
    # Remove empty nested sublists
    markdown = re.sub(
        r"^\s*(\w+\.|\*|\+|\-) (\w+\.|\*|\+|\-)\s*$", "", markdown, flags=re.MULTILINE
    )
    return markdown


def _save_markdown_to_file(document: Document, common_base_url: str) -> None:
    assert document.source
    file_path = "chunks-log/" + document.source.removeprefix(common_base_url).rstrip("/")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    logger.info("Saving markdown to %r", f"{file_path}.md")
    assert document.content
    Path(f"{file_path}.md").write_text(document.content, encoding="utf-8")


def _save_splits_to_files(
    file_path: str, uri: str, content: str, splits: list[SplitWithContextText], tree: Tree
) -> None:  # pragma: no cover
    logger.info("Saving chunks to %r", file_path)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as file:
        file.write(f"{uri} => {len(splits)} chunks\n")
        file.write("\n")
        for split in splits:
            file.write(f">>> {split.chunk_id!r} (length {split.token_count}) {split.headings}\n")
            file.write(split.text)
            file.write("\n--------------------------------------------------\n")
        file.write("\n\n")
        json_str = json.dumps([split.__dict__ for split in splits], indent=2)
        file.write(json_str)
        file.write("\n\n")
        file.write(tree.format())
        file.write("\n\n")
        file.write(content)


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
    # Ensure a list and subsequent table are being split; https://edd.ca.gov/en/payroll_taxes/Due_Dates_Calendar/
    text = re.sub(
        r"^( *[\-\*\+] .*\n)\n^(\| )",
        rf"\1{MarkdownHeaderTextSplitter_DELIMITER}\2",
        text,
        flags=re.MULTILINE,
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
