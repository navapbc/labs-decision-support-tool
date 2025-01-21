import os
import tempfile

import pytest

from src.util.file_util import convert_to_utf8


@pytest.fixture
def utf8_file():
    """Create a temporary file with regular UTF-8 content"""
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as f:
        f.write("question,answer\nTest")
    yield f.name
    os.unlink(f.name)


@pytest.fixture
def utf8_bom_file():
    """Create a temporary file with UTF-8-BOM content. Fixture simulates Excel export"""
    with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
        # Write UTF-8 BOM followed by content
        f.write(b"\xef\xbb\xbfquestion,answer\nTest")
    yield f.name
    os.unlink(f.name)


def test_convert_utf8_regular(utf8_file):
    """Test converting a regular UTF-8 file"""
    content = convert_to_utf8(utf8_file)
    assert content == "question,answer\nTest"


def test_convert_utf8_bom(utf8_bom_file):
    """Test converting a UTF-8 with BOM file (Excel fixture)"""
    content = convert_to_utf8(utf8_bom_file)
    assert content == "question,answer\nTest"
