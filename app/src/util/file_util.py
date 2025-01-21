import os
from pathlib import PosixPath
from typing import Optional, Tuple
from urllib.parse import urlparse

import boto3
import botocore


def convert_to_utf8(file_path: str) -> str:
    """Convert file contents to UTF-8 without BOM characters from Excel. Return content as a UTF-8 string"""
    # Ref: https://stackoverflow.com/questions/8898294/convert-utf-8-with-bom-to-utf-8-with-no-bom-in-python/8898439#8898439
    try:
        with open(file_path, "r", encoding="utf-8-sig", newline="") as fp:
            return fp.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="utf-8", newline="") as fp:
            return fp.read()


##################################
# Path parsing utils
##################################


def is_s3_path(path: str | PosixPath) -> bool:
    return str(path).startswith("s3://")


def split_s3_url(path: str) -> Tuple[str, str]:
    parts = urlparse(path)
    bucket_name = parts.netloc
    prefix = parts.path.lstrip("/")
    return (bucket_name, prefix)


def get_s3_bucket(path: str) -> Optional[str]:
    return urlparse(path).hostname


def get_s3_file_key(path: str) -> str:
    return urlparse(path).path[1:]


def get_file_name(path: str) -> str:
    return os.path.basename(path)


def get_files(path: str) -> list[str]:
    """Return a list of paths to all files in a directory, whether on local disk or on S3"""
    if is_s3_path(path):
        bucket_name, prefix = split_s3_url(path)
        s3 = boto3.resource("s3")
        bucket = s3.Bucket(bucket_name)
        files = [f"s3://{bucket_name}/{obj.key}" for obj in bucket.objects.filter(Prefix=prefix)]
        return files

    return [str(file) for file in PosixPath(path).rglob("*") if file.is_file()]


##################################
# S3 Utilities
##################################


def get_s3_client(boto_session: Optional[boto3.Session] = None) -> botocore.client.BaseClient:
    """Returns an S3 client, wrapping around boiler plate if you already have a session"""
    if boto_session:
        return boto_session.client("s3")

    return boto3.client("s3")
