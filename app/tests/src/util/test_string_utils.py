from src.util import string_utils


def test_split_paragraph():
    text = "This is a sentence. This is another sentence. This is a third sentence."
    char_limit = 30
    expected = [
        "This is a sentence.",
        "This is another sentence.",
        "This is a third sentence.",
    ]
    assert string_utils.split_paragraph(text, char_limit) == expected


def test_split_paragraph_on_overly_long_sentence():
    text = "This is a sentence. This is a really, really long sentence. This is a third sentence."
    char_limit = 30
    expected = [
        "This is a sentence.",
        "This is a really,",
        " really long sentence.",
        "This is a third sentence.",
    ]
    assert string_utils.split_paragraph(text, char_limit) == expected
