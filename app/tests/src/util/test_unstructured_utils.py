from smart_open import open as smart_open

from src.util.unstructured_utils import get_json_from_file


def test_get_json_from_file():
    with smart_open("/app/tests/docs/100.pdf", "rb") as file:
        elements = get_json_from_file(file)
        first_element = elements[0]
        assert len(elements) == 31
        assert first_element.metadata.page_number == 1
        assert first_element.text == "BPB 2023-006"
        assert first_element.category == "Header"
