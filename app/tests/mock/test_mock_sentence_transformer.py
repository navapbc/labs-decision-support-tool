from tests.mock.mock_sentence_transformer import MockSentenceTransformer


def test_mock_sentence_transformer():
    embedding_model = MockSentenceTransformer()

    assert embedding_model.max_seq_length == 512
    assert embedding_model.tokenizer.tokenize("Hello, world!") == ["Hello,", "world!"]
    assert len(embedding_model.encode("Hello, world!")) == 768

    # Test that we can compare similarity with dot product,
    # where sentences with the same average length word are considered more similar
    long_text = embedding_model.encode(
        "Incomprehensibility characterizes unintelligible, overwhelmingly convoluted dissertations."
    )
    medium_text = embedding_model.encode(
        "Curiosity inspires creative, innovative communities worldwide."
    )
    short_text = embedding_model.encode("The quick brown red fox jumps.")

    def dot_product(v1, v2):
        return sum(x * y for x, y in zip(v1, v2, strict=True))

    assert dot_product(long_text, long_text) > dot_product(long_text, medium_text)
    assert dot_product(long_text, medium_text) > dot_product(long_text, short_text)
    assert dot_product(medium_text, medium_text) > dot_product(medium_text, short_text)
