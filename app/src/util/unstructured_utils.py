import json
import pprint
import re
import tempfile

import requests
from unstructured.partition.pdf import partition_pdf


def get_json_from_file(filepath):
    elements = partition_pdf(filepath, strategy="fast")
    return [element.to_dict() for element in elements]


def get_file_from_url(url):
    response = requests.get(url)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_file.write(response.content)
    return temp_file.name


def get_json_from_url(url):
    temp_file_path = get_file_from_url(url)
    return get_json_from_file(temp_file_path)
