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
nltk.data.path.clear()
nltk.data.path.append(_nltk_data_path)


def split_paragraph(text: str, char_limit: int) -> list[str]:
    try:
        # https://stackoverflow.com/questions/44857382/change-nltk-download-path-directory-from-default-ntlk-data
        nltk.data.find("tokenizers/punkt_tab")
    except LookupError:
        nltk.download("punkt_tab", download_dir=_nltk_data_path)

    # Use the nltk sentence tokenizer to split the text into sentences
    # Could use spacy instead for more customization
    sents = sent_tokenize(text)
    return _join_up_to(sents, char_limit)


def _join_up_to(lines: list[str], char_limit: int, delimiter: str = " ") -> list[str]:
    "Join sentences or words in lines up to a character limit"
    chunks = []
    chunk = ""
    for line in lines:
        test_chunk = delimiter.join([chunk, line]) if chunk else line
        if len(test_chunk) > char_limit:
            # Don't use test_chunk; start a new chunk
            chunks.append(chunk)
            if len(line) < char_limit:
                chunk = line
            else:
                # Split into phrases; could use spacy instead for more robust splitting
                words = re.split(r"([,;])", line)
                logger.warning("Splitting sentence: %s", line)

                chunks += _join_up_to(words, char_limit=char_limit, delimiter="")
                # Start new empty chunk
                chunk = ""
        else:
            chunk = test_chunk

    # Add the last chunk
    chunks.append(chunk)
    return chunks
