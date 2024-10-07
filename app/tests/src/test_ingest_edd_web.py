import json
import logging

import pytest
from sqlalchemy import delete, select

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
        ]
    )


@pytest.fixture
def guru_local_file(tmp_path, sample_cards):
    file_path = tmp_path / "edd_scrapings.json"
    file_path.write_text(sample_cards)
    return str(file_path)


@pytest.fixture
def guru_s3_file(mock_s3_bucket_resource, sample_cards):
    mock_s3_bucket_resource.put_object(Body=sample_cards, Key="edd_scrapings.json")
    return "s3://test_bucket/edd_scrapings.json"


doc_attribs = {
    "dataset": "edd_web",
    "program": "employment",
    "region": "California",
}


@pytest.mark.parametrize("file_location", ["local", "s3"])
def test__ingest_edd(app_config, db_session, guru_local_file, guru_s3_file, file_location):
    db_session.execute(delete(Document))

    if file_location == "local":
        _ingest_edd_web(db_session, guru_local_file, doc_attribs)
    else:
        _ingest_edd_web(db_session, guru_s3_file, doc_attribs)

    documents = db_session.execute(select(Document).order_by(Document.name)).scalars().all()
    assert len(documents) == 2

    # TODO: assert document and chunk contents
