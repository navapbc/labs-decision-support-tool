from src.util.unstructured_utils import get_json_from_file
from smart_open import open as smart_open


def test_get_json_from_file():
    with smart_open("/app/tests/docs/100.pdf", "rb") as file:
        elements = get_json_from_file(file)
        assert elements == ""
        first_element = elements[0]
        assert len(elements) == 91
        assert first_element["metadata"] == {
            "filename": "/app/tests/docs/100.pdf",
            "page_number": 1,
        }
        assert first_element["text"] == "BEM 100"
        assert first_element["type"] == "Title"
