import difflib
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


def count_diffs(str1, str2):
    diffs = difflib.ndiff(str1, str2)
    return sum(1 for line in diffs if line.startswith("+ ") or line.startswith("- "))


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


def split_list(text: str, char_limit: int, has_intro_sentence: bool = True) -> list[str]:
    """
    Split text containing a list of items into chunks having up to a character limit each.
    The first line is treated as an introductory sentence, which will be repeated as the first line of each chunk.
    The first line and each list item should be separated by a newline character.
    """
    _prep_nltk_tokenizer()

    lines = text.split("\n")
    if has_intro_sentence:
        intro_sentence = lines[0]
        list_items = lines[1:]
    else:
        intro_sentence = ""
        list_items = lines

    # len(lines) accounts for the number of newline characters
    list_items_char_limit = char_limit - len(intro_sentence) - len(lines)
    chunks = [
        f"{intro_sentence}\n{chunk}"
        for chunk in _join_up_to(list_items, list_items_char_limit, delimiter="\n")
    ]
    assert all(len(chunk) <= char_limit for chunk in chunks)
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
    # Hint: Use https://regex101.com/ to create and test regex
    markdown = re.sub(r"\]\((?!\/|\#|https?:\/\/)", rf"]({base_url}", markdown)
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
            (remove_links(doc.metadata[key]) if key in doc.metadata else "")
            for key in MARKDOWN_METADATA_KEYS
        ]
        # Remove empty headings at the end of list
        while headings and not headings[-1]:
            headings.pop()
        yield tuple(headings), doc.page_content


def headings_as_markdown(headings: Sequence[str]) -> str:
    return "\n".join(f"{"#" * i} {h}" for i, h in enumerate(headings, start=1) if h)


def parse_heading_markdown(md: str) -> tuple[int, str]:
    match = re.match("^#+ ", md)
    if match:
        prefix = match.group()
        return prefix.count("#"), md.removeprefix(prefix)
    raise ValueError(f"Unable to parse markdown heading: {md!r}")


def remove_links(markdown: str) -> str:
    # Remove markdown links, e.g., `[This is a link](https://example.com/relative/path) and [another](https://example.com/absolute/path)` -> `This is a link and another`
    return re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", markdown)
