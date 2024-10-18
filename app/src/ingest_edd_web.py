import json
import logging
import sys
from typing import Sequence

from smart_open import open as smart_open

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.util.ingest_utils import add_embeddings, process_and_ingest_sys_args, tokenize
from src.util.string_utils import headings_as_markdown, remove_links, split_markdown_by_heading

logger = logging.getLogger(__name__)


def _ingest_edd_web(
    db_session: db.Session,
    json_filepath: str,
    doc_attribs: dict[str, str],
) -> None:
    with smart_open(json_filepath, "r", encoding="utf-8") as json_file:
        json_items = json.load(json_file)

    # First, split all json_items into chunks (fast) to debug any issues quickly
    for document, chunks, splits in _create_chunks(json_items, doc_attribs):
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

    def add_if_within_limit(self, paragraph: str) -> bool:
        new_text_to_encode = f"{self.text_to_encode}\n{remove_links(paragraph)}"
        token_count = len(tokenize(new_text_to_encode))
        if token_count <= app_config.sentence_transformer.max_seq_length:
            self.text += f"\n{paragraph}"
            self.text_to_encode = new_text_to_encode
            self.token_count = token_count
            return True
        return False

    def valid(self) -> bool:
        if self.token_count > app_config.sentence_transformer.max_seq_length:
            logger.warning(
                "Text too long with %i tokens: %s", self.token_count, self.text_to_encode
            )
            return False
        return True


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


def _split_heading_section(headings: Sequence[str], text: str) -> list[SplitWithContextText]:
    # Add headings to the context_str; other context can also be added
    context_str = headings_as_markdown(headings)
    logger.debug("New heading: %s", headings)

    splits: list[SplitWithContextText] = []
    # Split content by double newlines, then gather into the largest chunks
    # that tokenize to less than the max_seq_length
    paragraphs = text.split("\n")
    # Start new split with the first paragraph
    splits.append(SplitWithContextText(headings, paragraphs[0], context_str))
    for paragraph in paragraphs[1:]:
        if not paragraph:
            continue
        if splits[-1].add_if_within_limit(paragraph):
            logger.debug("adding to Split %i => %i tokens", len(splits), splits[-1].token_count)
        else:
            logger.info("Split %i has %i tokens", len(splits), splits[-1].token_count)
            # Start new split since longer_split will exceed max_seq_length
            splits.append(SplitWithContextText(headings, paragraph, context_str))

    if len(splits) == 1:
        logger.info("Heading section fits in 1 chunk: %s", headings[-1])
    else:
        logger.info("Split %i has %i tokens", len(splits), splits[-1].token_count)
        logger.info("Partitioned heading section into %i splits", len(splits))
        logger.debug("\n".join([f"[Split {i}]: {s.text_to_encode}" for i, s in enumerate(splits)]))

    for split in splits:
        assert (
            split.valid()
        ), f"token_count: {split.token_count} > {app_config.sentence_transformer.max_seq_length}"
    return splits


def main() -> None:
    process_and_ingest_sys_args(sys.argv, logger, _ingest_edd_web)


# if __name__ == "__main__":
#     from transformers.models.mpnet.tokenization_mpnet_fast import MPNetTokenizerFast

#     split = """# Unemployment Insurance – Forms and Publications
#     ## Publications

#     [DE 1275B](https://edd.ca.gov/siteassets/files/pdf_pub_ctr/de1275b.pdf) – English | [DE 1275B/A](https://edd.ca.gov/siteassets/files/pdf_pub_ctr/de1275ba.pdf) – Armenian
#     """
#     print(len(split))

#     sentence_transformer = app_config.sentence_transformer
#     embedding = sentence_transformer.encode(split, show_progress_bar=True)
#     embedding2 = sentence_transformer.encode(split + "blah " * 200, show_progress_bar=True)
#     print(f"{embedding.shape}")
#     print(f"{embedding2.shape}")
#     print(f"{embedding == embedding2}")

#     # sentence_transformer.tokenizer.clean_up_tokenization_spaces=True
#     print(sentence_transformer.tokenizer.__class__)
#     print(sentence_transformer.tokenizer)
#     tokens0 = sentence_transformer.tokenizer.tokenize(split, add_special_tokens=True)
#     # tokens0 = sentence_transformer.tokenizer.encode_plus(split).tokens()
#     print(len(tokens0))
#     print(tokens0)
#     tokens = sentence_transformer.tokenize([split])
#     print(tokens["input_ids"].shape)
#     print(tokens["input_ids"])
#     print(tokens["input_ids"][0])
#     tokens = sentence_transformer.tokenize([split * 2])
#     print(tokens["input_ids"].shape)
