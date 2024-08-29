from unstructured.partition.pdf import partition_pdf
from unstructured.documents.elements import Element
from typing import BinaryIO


def get_json_from_file(file: BinaryIO) -> list[Element]:
    elements = partition_pdf(filename=file, strategy="fast")
    return elements
