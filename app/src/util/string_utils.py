import logging
import os
import re
from typing import Optional

import nltk
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


def _join_up_to(lines: list[str], char_limit: int, delimiter: str = " ") -> list[str]:
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
