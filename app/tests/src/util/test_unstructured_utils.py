from src.util.unstructured_utils import get_json_from_file


def test_get_json_from_file():
    elements = get_json_from_file("/app/tests/docs/100.pdf")
    first_element = elements[0]
    assert len(elements) == 91
    assert first_element["metadata"] == {"filename": "/app/tests/docs/100.pdf", "page_number": 1}
    assert first_element["text"] == "BEM 100"
    assert first_element["type"] == "Title"
