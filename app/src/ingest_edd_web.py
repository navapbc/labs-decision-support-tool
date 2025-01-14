import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Callable, Optional, Sequence

from smart_open import open as smart_open

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.ingestion.markdown_chunking import chunk_tree
from src.ingestion.markdown_tree import create_markdown_tree
from src.util.ingest_utils import (
    ChunkingConfig,
    DefaultChunkingConfig,
    add_embeddings,
    create_file_path,
    deconstruct_list,
    deconstruct_table,
    document_exists,
    load_or_save_doc_markdown,
    process_and_ingest_sys_args,
    reconstruct_list,
    reconstruct_table,
    tokenize,
)
from src.util.string_utils import remove_links, split_markdown_by_heading

logger = logging.getLogger(__name__)


class Split:

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

        # For debugging tree-based chunking
        self.chunk_id = ""
        self.data_ids = ""

    @staticmethod
    def from_dict(split_dict: dict[str, str]) -> "Split":
        split = Split(
            split_dict["headings"],
            split_dict["text"],  # text used for citations
            "",
            split_dict["text_to_encode"],  # text used for embeddings
        )
        split.chunk_id = split_dict.get("chunk_id", "")
        split.data_ids = split_dict.get("data_ids", "")
        return split


class HeadingBasedSplit(Split):

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
    md_base_dir: str = "edd_md",
    skip_db: bool = False,
    resume: bool = False,
) -> None:
    def prep_json_item(item: dict[str, str]) -> dict[str, str]:
        markdown = item.get("main_content", item.get("main_primary", None))
        assert markdown, f"Item {item['url']} has no main_content or main_primary"
        item["markdown"] = _fix_input_markdown(markdown)
        return item

    common_base_url = "https://edd.ca.gov/en/"
    ingest_json(
        db_session,
        json_filepath,
        doc_attribs,
        md_base_dir,
        common_base_url,
        skip_db,
        resume,
        prep_json_item,
    )


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


def ingest_json(
    db_session: db.Session,
    json_filepath: str,
    doc_attribs: dict[str, str],
    md_base_dir: str,
    common_base_url: str,
    skip_db: bool = False,
    resume: bool = False,
    prep_json_item: Callable[[dict[str, str]], dict[str, str]] = lambda x: x,
    chunking_config: Optional[ChunkingConfig] = None,
) -> None:
    json_items = load_json_items(db_session, json_filepath, doc_attribs, skip_db, resume)

    for item in json_items:
        item = prep_json_item(item)

    if not chunking_config:
        chunking_config = DefaultChunkingConfig()
    # First, chunk all json_items into splits (fast) to debug any issues quickly
    all_splits = _chunk_into_splits_from_json(
        md_base_dir, json_items, doc_attribs, common_base_url, chunking_config
    )

    if skip_db:
        logger.info("Skip saving to DB")
    else:
        # Then save to DB, which is slow since embeddings are computed
        save_to_db(db_session, resume, all_splits)


def load_json_items(
    db_session: db.Session,
    json_filepath: str,
    doc_attribs: dict[str, str],
    skip_db: bool = False,
    resume: bool = False,
) -> Sequence[dict[str, str]]:
    with smart_open(json_filepath, "r", encoding="utf-8") as json_file:
        json_items = json.load(json_file)

    def verbose_document_exists(item: dict[str, str]) -> bool:
        if skip_db:
            logger.debug("Skip DB lookup for %s", item["url"])
        elif document_exists(db_session, item["url"], doc_attribs):
            logger.info("Skipping -- document already exists in DB: %s", item["url"])
            return True
        return False

    if resume:
        json_items = [item for item in json_items if not verbose_document_exists(item)]

    return json_items


def save_to_db(
    db_session: db.Session,
    resume: bool,
    all_splits: Sequence[tuple[Document, Sequence[Split]]],
) -> None:
    for document, splits in all_splits:
        if not splits:
            logger.warning("No chunks for %r", document.source)
            continue

        logger.info("Adding embeddings for %r", document.source)
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
        # Add embedding of text_to_encode to each chunk (slow)
        add_embeddings(chunks, [s.text_to_encode for s in splits])
        logger.info("  Embedded webpage across %d chunks: %r", len(chunks), document.name)

        # Then, add to the database
        db_session.add(document)
        db_session.add_all(chunks)
        if resume:
            db_session.commit()


def _chunk_into_splits_from_json(
    md_base_dir: str,
    json_items: Sequence[dict[str, str]],
    doc_attribs: dict[str, str],
    common_base_url: str,
    chunking_config: ChunkingConfig,
) -> Sequence[tuple[Document, Sequence[Split]]]:
    urls_processed: set[str] = set()
    result = []
    for item in json_items:
        assert "url" in item, f"Item {item['url']} has no url"
        url = item["url"]
        if url in urls_processed:
            # Workaround for duplicate items from web scraping
            logger.warning("Skipping duplicate URL: %s", url)
            continue

        logger.info("Processing: %s", url)
        urls_processed.add(url)

        assert "title" in item, f"Item {url} has no title"
        assert "markdown" in item, f"Item {url} has no markdown content"
        document = Document(name=item["title"], content=item["markdown"], source=url, **doc_attribs)

        file_path = create_file_path(md_base_dir, common_base_url, url)
        load_or_save_doc_markdown(file_path, document)

        chunks_file_path = f"{file_path}.splits.json"
        if os.path.exists(chunks_file_path):
            # Load the splits from the file in case they've been manually edited
            splits_dicts = json.loads(Path(chunks_file_path).read_text(encoding="utf-8"))
            splits: Sequence[Split] = [Split.from_dict(split_dict) for split_dict in splits_dicts]
            logger.info("  Loaded %d splits from file: %r", len(splits), chunks_file_path)
        else:
            splits = _chunk_page(document, chunking_config)
            logger.info("  Chunked into %d splits: %r", len(splits), document.name)
            _save_splits_to_files(chunks_file_path, url, splits)

        result.append((document, splits))
    logger.info(
        "=== DONE splitting all %d webpages into a total of %d chunks",
        len(json_items),
        sum(len(splits) for _, splits in result),
    )
    return result


USE_MARKDOWN_TREE = True


def _chunk_page(document: Document, chunking_config: ChunkingConfig) -> Sequence[Split]:
    if USE_MARKDOWN_TREE:
        return _create_splits_using_markdown_tree(document, chunking_config)
    else:
        return _create_splits_using_headings(document)


def _create_splits_using_markdown_tree(
    document: Document, chunking_config: ChunkingConfig
) -> list[Split]:
    splits: list[Split] = []
    try:
        assert document.content
        tree = create_markdown_tree(
            document.content, doc_name=document.name, doc_source=document.source
        )
        tree_chunks = chunk_tree(tree, chunking_config)

        # For debugging, save the tree to a file
        if os.path.exists("DEBUG_TREE"):
            assert document.source
            tree_file_path = f"{document.source.rsplit('/', 1)[-1]}.tree"
            Path(tree_file_path).write_text(tree.format(), encoding="utf-8")

        for chunk in tree_chunks:
            split = Split(chunk.headings, chunk.markdown, chunk.context_str, chunk.embedding_str)
            assert split.token_count == chunk.length
            splits.append(split)

            # Add extra info for debugging
            split.chunk_id = chunk.id
            split.data_ids = ", ".join(chunk.data_ids)
    except (Exception, KeyboardInterrupt) as e:  # pragma: no cover
        logger.error("Error chunking %s (%s): %s", document.name, document.source, e)
        logger.error(tree.format())
        raise e
    return splits


def _save_splits_to_files(file_path: str, uri: str, splits: Sequence[Split]) -> None:
    logger.info("  Saving splits to %r", file_path)
    splits_json = json.dumps([split.__dict__ for split in splits], indent=2)
    Path(file_path).write_text(splits_json, encoding="utf-8")

    # Save prettified splits to a markdown file for manual inspection
    with open(f"{os.path.splitext(file_path)[0]}.md", "w", encoding="utf-8") as file:
        file.write(f"{uri} => {len(splits)} splits\n")
        file.write("\n")
        for split in splits:
            file.write(
                f"---\nchunk_id: {split.chunk_id}\nlength:   {split.token_count}\nheadings: {split.headings}\n---\n"
            )
            file.write(split.text)
            file.write("\n====================================\n")
        file.write("\n\n")


# endregion
# region Splitting Markdown by Headings


def _create_splits_using_headings(document: Document) -> Sequence[Split]:
    splits = []
    assert document.content
    for headings, text in split_markdown_by_heading(f"# {document.name}\n\n" + document.content):
        # Start a new split for each heading
        section_splits = _split_heading_section(headings, text)
        splits.extend(section_splits)
    return splits


# MarkdownHeaderTextSplitter splits text by "\n" then calls aggregate_lines_to_chunks() to reaggregate
# paragraphs using "  \n", so "\n\n" is replaced by "  \n"
MarkdownHeaderTextSplitter_DELIMITER = "  \n"


def _split_heading_section(headings: Sequence[str], text: str) -> list[HeadingBasedSplit]:
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

    splits: list[HeadingBasedSplit] = []
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
    splits: list[HeadingBasedSplit],
    paragraphs: Sequence[str],
    delimiter: str = "\n\n",
) -> None:
    splits.append(HeadingBasedSplit(headings, paragraphs[0], context_str))
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
            splits.append(HeadingBasedSplit(headings, paragraph, context_str))
    _split_large_text_block(headings, context_str, splits)

    for split in splits:
        assert (
            not split.exceeds_limit()
        ), f"token_count: {split.token_count} > {app_config.sentence_transformer.max_seq_length}"


def _split_large_text_block(
    headings: Sequence[str], context_str: str, splits: list[HeadingBasedSplit]
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


# endregion


def main() -> None:
    process_and_ingest_sys_args(sys.argv, logger, _ingest_edd_web)
