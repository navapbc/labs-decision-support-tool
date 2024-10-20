import logging
import os
import re
from typing import Iterator, Optional, Sequence
from urllib.parse import urlparse

import nltk
from langchain_text_splitters import MarkdownHeaderTextSplitter
from nltk.tokenize import sent_tokenize

logger = logging.getLogger(__name__)


def join_list(joining_list: Optional[list], join_txt: str = "\n") -> str:
    """
    Utility to join a list.

    Functionally equivalent to:
    "" if joining_list is None else "\n".join(joining_list)
    """
    if not joining_list:
        return ""

    return join_txt.join(joining_list)


def basic_ascii(text: str) -> str:
    # See https://www.ascii-code.com/
    return "".join([c if 32 <= ord(c) <= 126 else " " for c in text])


# Set the nltk.data.path to a relative directory so that it's available in the Docker environment
_nltk_data_path = os.path.abspath("./nltk_data")


def _prep_nltk_tokenizer() -> None:
    if _nltk_data_path not in nltk.data.path:
        nltk.data.path.append(_nltk_data_path)
    try:
        # https://stackoverflow.com/questions/44857382/change-nltk-download-path-directory-from-default-ntlk-data
        nltk.data.find("tokenizers/punkt_tab")
    except LookupError:
        nltk.download("punkt_tab", download_dir=_nltk_data_path)


def split_paragraph(text: str, char_limit: int) -> list[str]:
    _prep_nltk_tokenizer()

    # Use the nltk sentence tokenizer to split the text into sentences
    # Could use spacy instead for more customization
    sents = sent_tokenize(text)
    if len(sents) == 1:
        # 400.pdf page 73 has tables that result in large paragraphs
        sents = text.split("\n\n")
        return _join_up_to(sents, char_limit, delimiter="\n\n")

    return _join_up_to(sents, char_limit)


def split_list(
    markdown: str,
    char_limit: int,
    has_intro_sentence: bool = False,
    list_delimiter: str = r"^( *[\-\*\+] )",
) -> list[str]:
    """
    Split markdown containing a list of items into chunks having up to a character limit each.
    The first split may be treated as an introductory sentence, which will be repeated as the first line of each chunk.
    Each list item should begin with the list_delimiter regex.
    """
    intro_sentence, list_items = deconstruct_list(markdown, has_intro_sentence, list_delimiter)
    return reconstruct_list(char_limit, intro_sentence, list_items, join_delimiter="")


def deconstruct_list(
    markdown: str, has_intro_sentence: bool = False, list_delimiter: str = r"^( *[\-\*\+] )"
) -> tuple[str, list[str]]:
    "Deconstruct a list of items into an introductory sentence and a list of items"
    splits = re.split(list_delimiter, markdown, flags=re.MULTILINE)
    if has_intro_sentence or not markdown.startswith(list_delimiter):
        intro_sentence = splits[0]
        splits = splits[1:]
    else:
        intro_sentence = ""

    # Reconstruct each list item
    list_items = [(splits[a] + splits[a + 1]) for a in range(0, len(splits), 2)]
    return intro_sentence, list_items


def reconstruct_list(
    char_limit: int, intro_sentence: str, list_items: Sequence[str], join_delimiter: str = ""
) -> list[str]:
    "Reconstruct a list of items into chunks (with same intro_sentence) having up to a character limit each"
    # Before the set of list items, there should be a blank line
    intro_sentence = ensure_blank_line_suffix(intro_sentence)

    list_items_char_limit = char_limit - len(intro_sentence)
    chunks = [
        intro_sentence + some_list_items
        for some_list_items in _join_up_to(
            list_items, list_items_char_limit, delimiter=join_delimiter
        )
    ]
    assert all(len(chunk) <= char_limit for chunk in chunks)
    return chunks


def ensure_blank_line_suffix(text: str) -> str:
    "Return text with a blank line after the text"
    if not text.endswith("\n\n"):
        if text.endswith("\n"):
            text += "\n"
        else:
            text += "\n\n"
    return text


def deconstruct_table(
    markdown: str, has_intro_sentence: bool = False, list_delimiter: str = r"^(\| )"
) -> tuple[str, str, list[str]]:
    "Deconstruct a table of items into an introductory sentence, a table header, and a list of items"
    intro_sentence, list_items = deconstruct_list(markdown, has_intro_sentence, list_delimiter)

    if list_items[1].startswith("| --- |"):
        table_header = list_items.pop(0) + list_items.pop(0)

    return intro_sentence, table_header, list_items


def reconstruct_table(
    char_limit: int,
    intro_sentence: str,
    table_header: str,
    table_rows: Sequence[str],
    join_delimiter: str = "",
) -> list[str]:
    "Reconstruct a table of items into chunks (with intro_sentence + table_header) having up to a character limit each."

    # Before the table, there should be a blank line
    intro_sentence = ensure_blank_line_suffix(intro_sentence)

    intro = intro_sentence + table_header
    table_char_limit = char_limit - len(intro)
    chunks = [
        intro + some_table_rows
        for some_table_rows in _join_up_to(table_rows, table_char_limit, delimiter=join_delimiter)
    ]
    assert all(len(chunk) <= char_limit for chunk in chunks), [len(chunk) for chunk in chunks]
    return chunks


def _join_up_to(lines: Sequence[str], char_limit: int, delimiter: str = " ") -> list[str]:
    "Join sentences or words in lines up to a character limit"
    chunks = []
    chunk = ""
    for line in lines:
        test_chunk = delimiter.join([chunk, line]) if chunk else line
        if len(test_chunk) > char_limit:
            # Don't use test_chunk; start a new chunk
            if chunk:
                chunks.append(chunk)
            if len(line) < char_limit:
                chunk = line
            else:
                # Split into phrases; could use spacy instead for more robust splitting
                words = re.split(r"([,;\n])", line)
                logger.warning("Splitting sentence: %s", line[:120])

                chunks += _join_up_to(words, char_limit=char_limit, delimiter="")
                # Start new empty chunk
                chunk = ""
        else:
            chunk = test_chunk

    # Add the last chunk
    chunks.append(chunk)

    assert all(len(chunk) <= char_limit for chunk in chunks)
    return chunks


def resolve_urls(base_url: str, markdown: str) -> str:
    "Replace non-absolute URLs in markdown with absolute URLs."
    parsed = urlparse(base_url)
    domain_prefix = parsed.scheme + "://" + parsed.netloc + "/"
    # Scenario 1: link starts with '/' like "/en/unemployment/"
    # Prepend the domain prefix to the link
    markdown = re.sub(r"\]\(\/", rf"]({domain_prefix}", markdown)
    # Scenario 2: link does not start with '/' or "http://" or "https://", like "unemployment/"
    # Insert the base URL of the web page before the link
    if not base_url.endswith("/"):
        base_url += "/"
    markdown = re.sub(r"\]\((?!\/|https?:\/\/)", rf"]({base_url}", markdown)
    return markdown


MARKDOWN_HEADER_TUPLES = [
    ("#", "H1"),
    ("##", "H2"),
    ("###", "H3"),
    ("####", "H4"),
    ("#####", "H5"),
    ("######", "H6"),
]

MARKDOWN_METADATA_KEYS = [key for _, key in MARKDOWN_HEADER_TUPLES]


def split_markdown_by_heading(markdown: str) -> Iterator[tuple[Sequence[str], str]]:
    markdown_splitter = MarkdownHeaderTextSplitter(MARKDOWN_HEADER_TUPLES)
    for doc in markdown_splitter.split_text(markdown):
        headings = [
            # Strip out the markdown link syntax from the headings
            (
                re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", doc.metadata[key])
                if key in doc.metadata
                else ""
            )
            for key in MARKDOWN_METADATA_KEYS
        ]
        # Remove empty headings at the end of list
        while headings and not headings[-1]:
            headings.pop()
        yield tuple(headings), doc.page_content


def headings_as_markdown(headings: Sequence[str]) -> str:
    return "\n".join(f"{"#" * i} {h}" for i, h in enumerate(headings, start=1) if h)


def remove_links(markdown: str) -> str:
    return re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", markdown)
