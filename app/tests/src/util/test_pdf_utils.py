from src.util.pdf_utils import Heading, extract_outline


def test_extract_outline():
    # Create a PDF with a heading hierarchy
    with open("/app/tests/docs/707.pdf", "rb") as fp:
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
