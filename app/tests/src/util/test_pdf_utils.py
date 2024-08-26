import pytest

from src.util.pdf_utils import Heading, extract_outline, get_pdf_info


@pytest.mark.parametrize("count_pages", [False, True])
def test_get_pdf_info(count_pages):
    with open("/app/tests/src/util/707.pdf", "rb") as fp:
        pdf_info = get_pdf_info(fp, count_pages=count_pages)

        assert pdf_info.title == "TIME AND ATTENDANCE REVIEWS"
        assert pdf_info.creation_date == "D:20200106133617-05'00'"
        assert pdf_info.mod_date == "D:20200106133617-05'00'"
        assert pdf_info.producer == "Microsoft® Word for Office 365"
        if count_pages:
            assert pdf_info.page_count == 4
        else:
            assert pdf_info.page_count is None


def test_extract_outline():
    # Create a PDF with a heading hierarchy
    with open("/app/tests/src/util/707.pdf", "rb") as fp:
        outline = extract_outline(fp)

        expected_headings = [
            Heading(title="Overview", level=1, pageno=1),
            Heading(title="Rule Violations", level=1, pageno=1),
            Heading(title="Time and Attendance Review  Process", level=1, pageno=1),
            Heading(title="Provider Errors", level=2, pageno=1),
            Heading(title="Intentional Program Violations", level=2, pageno=2),
            Heading(title="Disqualifications", level=1, pageno=2),
            Heading(title="reconsidera-tions", level=1, pageno=3),
            Heading(title="Reconsideration process", level=1, pageno=3),
            Heading(
                title="Enrollment of a Provider after the Penalty Period has ended",
                level=1,
                pageno=4,
            ),
            Heading(title="legal base", level=1, pageno=4),
        ]
        assert outline == expected_headings
