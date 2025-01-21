import os
import tempfile
from pathlib import PosixPath
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.stub import Stubber

from src.util.file_util import (
    convert_to_utf8,
    get_file_name,
    get_files,
    get_s3_bucket,
    get_s3_client,
    get_s3_file_key,
    is_s3_path,
    split_s3_url,
)


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


@pytest.fixture
def s3_stub():
    """Create a stubbed S3 client for testing"""
    s3_client = boto3.client("s3")
    with Stubber(s3_client) as stubber:
        yield stubber


def test_convert_utf8_regular(utf8_file):
    """Test converting a regular UTF-8 file"""
    content = convert_to_utf8(utf8_file)
    assert content == "question,answer\nTest"


def test_convert_utf8_bom(utf8_bom_file):
    """Test converting a UTF-8 with BOM file (Excel fixture)"""
    content = convert_to_utf8(utf8_bom_file)
    assert content == "question,answer\nTest"


def test_is_s3_path():
    """Test S3 path detection"""
    assert is_s3_path("s3://bucket/key.csv") is True
    assert is_s3_path("/local/path/file.csv") is False
    assert is_s3_path(PosixPath("/local/path")) is False
    # PosixPath doesn't handle s3:// URLs, so we only test string paths for s3
    assert is_s3_path("s3://bucket/key") is True


def test_split_s3_url():
    """Test S3 URL splitting into bucket and key"""
    bucket, key = split_s3_url("s3://my-bucket/path/to/file.csv")
    assert bucket == "my-bucket"
    assert key == "path/to/file.csv"


def test_get_s3_bucket():
    """Test extracting S3 bucket from URL"""
    assert get_s3_bucket("s3://my-bucket/file.csv") == "my-bucket"
    assert get_s3_bucket("/local/path") is None


def test_get_s3_file_key():
    """Test extracting S3 key from URL"""
    assert get_s3_file_key("s3://bucket/path/to/file.csv") == "path/to/file.csv"


def test_get_file_name():
    """Test extracting filename from path"""
    assert get_file_name("/path/to/file.csv") == "file.csv"
    assert get_file_name("s3://bucket/path/file.csv") == "file.csv"


@pytest.mark.parametrize(
    "expected",
    [
        ["file1.txt", "file2.txt"],  # Local path test files
        ["s3://bucket/prefix/file1.txt"],  # S3 path test files
    ],
)
def test_get_files(expected, tmp_path):
    """Test getting files from both local and S3 paths"""
    if "s3://" in expected[0]:  # Test S3 path
        path = "s3://bucket/prefix"
        # Mock S3 resource and bucket
        mock_obj = MagicMock()
        mock_obj.key = "prefix/file1.txt"
        mock_bucket = MagicMock()
        mock_bucket.objects.filter.return_value = [mock_obj]

        with patch("boto3.resource") as mock_resource:
            mock_resource.return_value.Bucket.return_value = mock_bucket
            files = get_files(path)
            assert sorted(files) == sorted(expected)
            mock_bucket.objects.filter.assert_called_once_with(Prefix="prefix")
    else:  # Test local path
        # Create local test files in pytest-provided temp directory
        for filename in expected:
            (tmp_path / filename).touch()

        files = get_files(str(tmp_path))
        files = [os.path.basename(f) for f in files]
        assert sorted(files) == sorted(expected)


def test_get_s3_client():
    """Test S3 client creation"""
    # Test without session
    client = get_s3_client()
    assert client is not None

    # Test with session
    session = boto3.Session()
    client = get_s3_client(session)
    assert client is not None
