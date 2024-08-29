from typing import BinaryIO

from unstructured.documents.elements import Element
from unstructured.partition.pdf import partition_pdf


def get_json_from_file(file: BinaryIO) -> list[Element]:
    elements = partition_pdf(file=file, strategy="fast")
    return elements
