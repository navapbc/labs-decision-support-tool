from src.ingestion.pdf_elements import Heading
from src.ingestion.pdf_stylings import Styling, extract_stylings


def test_extract_styles():
    with open("/app/tests/src/util/707.pdf", "rb") as fp:
        _stylings = extract_stylings(fp)

    assert _stylings == []


all_expected_stylings = [
    Styling(
        text="CDC not eligible due to 6 month penalty period",
        pageno=3,
        headings=[Heading(title="Disqualifications", level=1, pageno=2)],
        wider_text="• First occurrence - six month disqualification. The "
        "closure reason will be CDC not eligible due to 6 month "
        "penalty period. ",
        bold=True,
    ),
    Styling(
        text="CDC not eligible due to 12 month penalty period. ",
        pageno=3,
        headings=[Heading(title="Disqualifications", level=1, pageno=2)],
        wider_text="• Second occurrence - twelve month disqualification. The "
        "closure reason will be CDC not eligible due to 12 month "
        "penalty period. ",
        bold=True,
    ),
    Styling(
        text="CDC not eligible due to lifetime penalty. ",
        pageno=3,
        headings=[Heading(title="Disqualifications", level=1, pageno=2)],
        wider_text="• Third occurrence - lifetime disqualification. The "
        "closure reason will be CDC not eligible due to lifetime "
        "penalty. ",
        bold=True,
    ),
    Styling(
        text="CDC penalty period has ended. See BEM 704 for re-enroll-ment requirements.",
        pageno=4,
        headings=[
            Heading(
                title="Enrollment of a Provider after the Penalty Period has ended",
                level=1,
                pageno=4,
            )
        ],
        wider_text="When the penalty period has ended, the closure reason "
        "will change to CDC penalty period has ended. See BEM 704 "
        "for re-enroll-ment requirements.",
        bold=True,
    ),
    Styling(
        text="CDC ",
        pageno=4,
        headings=[Heading(title="legal base", level=1, pageno=4)],
        wider_text="CDC ",
        bold=True,
    ),
]
