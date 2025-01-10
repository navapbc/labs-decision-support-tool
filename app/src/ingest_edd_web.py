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
    DefaultChunkingConfig,
    add_embeddings,
    create_file_path,
    document_exists,
    load_or_save_doc_markdown,
    process_and_ingest_sys_args,
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
) -> None:
    json_items = load_json_items(db_session, json_filepath, doc_attribs, skip_db, resume)

    for item in json_items:
        item = prep_json_item(item)

    # First, chunk all json_items into splits (fast) to debug any issues quickly
    all_splits = _chunk_into_splits_from_json(md_base_dir, json_items, doc_attribs, common_base_url)

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
            splits = _chunk_page(document)
            logger.info("  Chunked into %d splits: %r", len(splits), document.name)
            _save_splits_to_files(chunks_file_path, url, splits)

        result.append((document, splits))
    logger.info(
        "=== DONE splitting all %d webpages into a total of %d chunks",
        len(json_items),
        sum(len(splits) for _, splits in result),
    )
    return result




def _chunk_page(document: Document) -> Sequence[Split]:
    return _create_splits_using_markdown_tree(document)


def _create_splits_using_markdown_tree(document: Document) -> list[Split]:
    splits: list[Split] = []
    chunking_config = DefaultChunkingConfig()
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


def main() -> None:
    process_and_ingest_sys_args(sys.argv, logger, _ingest_edd_web)
