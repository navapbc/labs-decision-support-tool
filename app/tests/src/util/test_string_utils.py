from src.util import string_utils


def test_split_paragraph():
    text = "This is a sentence. This is another sentence. This is a third sentence."
    assert string_utils.split_paragraph(text, 30) == [
        "This is a sentence.",
        "This is another sentence.",
        "This is a third sentence.",
    ]


def test_split_paragraph_on_overly_long_sentence():
    text = "This is a sentence. This is a really, really long sentence. This is a third sentence."
    assert string_utils.split_paragraph(text, 30) == [
        "This is a sentence.",
        "This is a really,",
        " really long sentence.",
        "This is a third sentence.",
    ]


def test_split_list():
    text = (
        "Following are list items:\n"
        "    - This is a sentence.\n"
        "    - This is another sentence.\n"
        "    - This is a third sentence."
    )
    assert string_utils.split_list(text, 90) == [
        (
            "Following are list items:\n"
            "    - This is a sentence.\n"
            "    - This is another sentence."
        ),
        ("Following are list items:\n    - This is a third sentence."),
    ]


def test_resolve_urls_scenario1():
    base_url = "https://example.com"
    markdown = "[This is a link](/relative/path) and [another](https://example.com/absolute/path)"
    assert (
        string_utils.resolve_urls(base_url, markdown)
        == "[This is a link](https://example.com/relative/path) and [another](https://example.com/absolute/path)"
    )


def test_resolve_urls_scenario2():
    base_url = "https://example.com/some_webpage"
    markdown = "[This is a link](relative/path) and [another](path2/index.html)"
    assert (
        string_utils.resolve_urls(base_url, markdown)
        == "[This is a link](https://example.com/some_webpage/relative/path) and [another](https://example.com/some_webpage/path2/index.html)"
    )
