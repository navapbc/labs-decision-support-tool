import json
import logging

import pytest
from sqlalchemy import delete, select

from src.app_config import app_config as app_config_for_test
from src.db.models.document import Document
from src.ingest_edd_web import _ingest_edd_web


@pytest.fixture
def sample_cards():
    return json.dumps(
        [
            {
                "url": "https://edd.ca.gov/en/disability/options_to_file_for_di_benefits/",
                "title": "Options to File for Disability Insurance Benefits",
                "main_content": "Disability Insurance (DI) provides short-term, partial wage replacement ...\n\nIf you think you are eligible to [file a claim](/en/disability/apply/), review ...",
            },
            {
                "url": "https://edd.ca.gov/en/disability/options_to_file_for_di_benefits/",
                "title": "Options to File for Disability Insurance Benefits",
                "main_content": "Disability Insurance (DI) provides short-term, partial wage replacement ...\n\nIf you think you are eligible to [file a claim](/en/disability/apply/), review ...",
            },
            {
                "url": "https://edd.ca.gov/en/disability/nonindustrial/faqs/",
                "title": "Nonindustrial Disability Insurance FAQs",
                "main_content": """## Nonindustrial Disability Insurance\n\nGet answers to FAQs about Nonindustrial Disability Insurance (NDI) and Nonindustrial Disability Insurance-Family Care Leave (NDI-FCL).

## Can I participate in either State Disability Insurance (SDI), NDI, or Enhanced Nonindustrial Insurance (ENDI)?

No. You cannot choose your disability program. It is determined by your employment position and bargaining unit.

## Will the State continue to contribute to my health, dental, and vision benefits if I am unable to work and receive NDI benefits?

If you are enrolled in the Annual Leave Program (ALP), your employer will continue to pay benefits.
""",
                "nonaccordion": "## Nonindustrial Disability Insurance\n\nGet answers to FAQs about Nonindustrial Disability Insurance (NDI) and Nonindustrial Disability Insurance-Family Care Leave (NDI-FCL).",
                "accordions": {
                    "Can I participate in either State Disability Insurance (SDI), NDI, or Enhanced Nonindustrial Insurance (ENDI)?": [
                        "No. You cannot choose your disability program. It is determined by your employment position and bargaining unit."
                    ],
                    "Will the State continue to contribute to my health, dental, and vision benefits if I am unable to work and receive NDI benefits?": [
                        "If you are enrolled in the Annual Leave Program (ALP), your employer will continue to pay benefits."
                    ],
                },
            },
            {
                "url": "https://edd.ca.gov/en/payroll_taxes/suta_dumping/",
                "title": "State Unemployment Tax Act Dumping",
                "main_content": (
                    "### SUTA Dumping Hurts Everyone\n\n"
                    "Employers, employees, and taxpayers make up the difference in higher taxes, lost jobs, lost profits, lower wages, and higher costs for goods and services.\n\n"
                    "SUTA dumping:\n\n"
                    "* Costs the UI trust fund millions of dollars each year.\n"
                    "* Adversely affects tax rates for all employers.\n"
                    "* Creates inequity for compliant employers.\n"
                    "* Eliminates the incentive for employers to avoid layoffs.\n"
                    "* Compromises the integrity of the UI system.\n\n"
                    "### [SUTA Dumping Schemes](https://edd.ca.gov/en/payroll_taxes/suta_dumping/#collapse-2a82e068-3b29-4473-af7e-de9ea6961277)\n\n"
                    "These schemes are meant to unlawfully lower an employer\u2019s UI tax rate. Employers should know about these schemes and their potential legal ramifications.\n\n"
                ),
            },
            {
                "url": "https://edd.ca.gov/en/jobs_and_training/northern_region/",
                "title": "The Northern Job Fairs and Workshops",
                "main_primary": (
                    "## Scheduled Events\n\n"
                    "**Career Center Orientation**\n"
                    "| Location | Date/Time | Other Information |\n"
                    "| --- | --- | --- |\n"
                    "| Virtual | Friday | This workshop will ... |\n"
                    "| Virtual | Friday | This workshop is for ... |\n"
                    "| Virtual | Friday | Staff will conduct ... |\n"
                ),
            },
        ]
    )


@pytest.fixture
def edd_web_local_file(tmp_path, sample_cards):
    file_path = tmp_path / "edd_scrapings.json"
    file_path.write_text(sample_cards)
    return str(file_path)


@pytest.fixture
def edd_web_s3_file(mock_s3_bucket_resource, sample_cards):
    mock_s3_bucket_resource.put_object(Body=sample_cards, Key="edd_scrapings.json")
    return "s3://test_bucket/edd_scrapings.json"


doc_attribs = {
    "dataset": "edd_web",
    "program": "employment",
    "region": "California",
}


@pytest.mark.parametrize("file_location", ["local", "s3"])
def test__ingest_edd(
    caplog, app_config, db_session, edd_web_local_file, edd_web_s3_file, file_location
):
    # Force a short max_seq_length to test chunking
    app_config_for_test.sentence_transformer.max_seq_length = 47

    db_session.execute(delete(Document))

    with caplog.at_level(logging.WARNING):
        if file_location == "local":
            _ingest_edd_web(db_session, edd_web_local_file, doc_attribs)
        else:
            _ingest_edd_web(db_session, edd_web_s3_file, doc_attribs)

    documents = db_session.execute(select(Document).order_by(Document.name)).scalars().all()
    assert len(documents) == 4

    assert (
        "Skipping duplicate URL: https://edd.ca.gov/en/disability/options_to_file_for_di_benefits/"
        in caplog.messages[0]
    )

    assert documents[0].name == "Nonindustrial Disability Insurance FAQs"
    assert documents[0].source == "https://edd.ca.gov/en/disability/nonindustrial/faqs/"
    assert documents[1].name == "Options to File for Disability Insurance Benefits"
    assert (
        documents[1].source == "https://edd.ca.gov/en/disability/options_to_file_for_di_benefits/"
    )
    assert documents[2].name == "State Unemployment Tax Act Dumping"
    assert documents[2].source == "https://edd.ca.gov/en/payroll_taxes/suta_dumping/"
    assert documents[3].name == "The Northern Job Fairs and Workshops"
    assert documents[3].source == "https://edd.ca.gov/en/jobs_and_training/northern_region/"

    assert len(documents[0].chunks) == 3
    assert (
        documents[0].chunks[0].content
        == "Get answers to FAQs about Nonindustrial Disability Insurance (NDI) and Nonindustrial Disability Insurance-Family Care Leave (NDI-FCL)."
    )
    assert documents[0].chunks[0].headings == [
        "Nonindustrial Disability Insurance FAQs",
        "Nonindustrial Disability Insurance",
    ]

    assert len(documents[1].chunks) == 1
    assert (
        documents[1].chunks[0].content
        == "Disability Insurance (DI) provides short-term, partial wage replacement ...\n\nIf you think you are eligible to [file a claim](/en/disability/apply/), review ..."
    )
    assert documents[1].chunks[0].headings == ["Options to File for Disability Insurance Benefits"]

    # Document[2] has a list
    assert len(documents[2].chunks) == 4
    assert (
        documents[2].chunks[0].content
        == "Employers, employees, and taxpayers make up the difference in higher taxes, lost jobs, lost profits, lower wages, and higher costs for goods and services."
    )
    assert documents[2].chunks[0].headings == [
        "State Unemployment Tax Act Dumping",
        "",
        "SUTA Dumping Hurts Everyone",
    ]

    assert documents[2].chunks[1].content == (
        "SUTA dumping:\n\n"
        "* Costs the UI trust fund millions of dollars each year.\n"
        "* Adversely affects tax rates for all employers.\n"
        "* Creates inequity for compliant employers.\n"
        "* Eliminates the incentive for employers to avoid layoffs.\n"
    )
    assert documents[2].chunks[1].headings == [
        "State Unemployment Tax Act Dumping",
        "",
        "SUTA Dumping Hurts Everyone",
    ]

    assert documents[2].chunks[2].content == (
        "SUTA dumping:\n\n" "* Compromises the integrity of the UI system."
    )
    assert documents[2].chunks[2].headings == [
        "State Unemployment Tax Act Dumping",
        "",
        "SUTA Dumping Hurts Everyone",
    ]

    assert documents[2].chunks[3].content == (
        "These schemes are meant to unlawfully lower an employer\u2019s UI tax rate. Employers should know about these schemes and their potential legal ramifications."
    )
    assert documents[2].chunks[3].headings == [
        "State Unemployment Tax Act Dumping",
        "",
        "SUTA Dumping Schemes",
    ]

    # Document[3] has a table
    assert len(documents[3].chunks) == 2
    for chunk in documents[3].chunks:
        print("======")
        print(chunk.content)
    assert documents[3].chunks[0].content == (
        "**Career Center Orientation**\n\n"
        "| Location | Date/Time | Other Information |\n"
        "| --- | --- | --- |\n"
        "| Virtual | Friday | This workshop will ... |\n"
        "| Virtual | Friday | This workshop is for ... |\n"
    )
    assert documents[3].chunks[1].content == (
        "**Career Center Orientation**\n\n"
        "| Location | Date/Time | Other Information |\n"
        "| --- | --- | --- |\n"
        "| Virtual | Friday | Staff will conduct ... |"
    )
    for chunk in documents[3].chunks:
        assert chunk.headings == [
            "The Northern Job Fairs and Workshops",
            "Scheduled Events",
        ]
