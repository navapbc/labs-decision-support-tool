import pytest

from src.util.bem_util import (
    build_bem_document_name,
    build_pdf_page_url,
    extract_bem_number,
    is_pdf_url,
    normalize_bem_title,
)


def test_extract_bem_number():
    assert extract_bem_number("Please review BEM 123.") == "123"
    assert extract_bem_number("The policy in BEM 123A has been updated.") == "123A"
    with pytest.raises(ValueError):
        extract_bem_number("This is not a valid case: BEM123.")


def test_normalize_bem_title():
    assert normalize_bem_title("TIME AND ATTENDANCE REVIEWS") == "Time And Attendance Reviews"
    assert normalize_bem_title("Medical Assistance Program") == "Medical Assistance Program"


def test_build_bem_document_name():
    assert (
        build_bem_document_name("707", "TIME AND ATTENDANCE REVIEWS")
        == "BEM 707 — Time And Attendance Reviews"
    )


def test_is_pdf_url():
    assert is_pdf_url("http://localhost:8080/sources/bem-mobile.pdf")
    assert not is_pdf_url("https://example.com/policy-page")


def test_build_pdf_page_url():
    assert (
        build_pdf_page_url("http://localhost:8080/sources/bem-mobile.pdf", 7)
        == "http://localhost:8080/sources/bem-mobile.pdf#page=7"
    )
    assert (
        build_pdf_page_url("http://localhost:8080/sources/bem-mobile.pdf", None)
        == "http://localhost:8080/sources/bem-mobile.pdf"
    )
    assert build_pdf_page_url(None, 7) is None
