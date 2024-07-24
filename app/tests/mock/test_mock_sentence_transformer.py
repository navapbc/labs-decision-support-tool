import pytest
from sentence_transformers import SentenceTransformer, util

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


# This test doesn't normally run with the other tests because it requires downloading large embedding models.
# To run this test, remove the `manual_` prefix so that the function begins with `test_`.
# Run the test locally: pytest tests/mock/test_mock_sentence_transformer.py --capture=no -k test_sentence_transformer
# The embedding models will be downloaded automatically to ~/.cache/huggingface/hub, if it does not already exist.
@pytest.mark.parametrize(
    "embedding_model", ["multi-qa-mpnet-base-cos-v1", "multi-qa-mpnet-base-dot-v1"]
)
def manual_test_sentence_transformer(embedding_model):
    transformer = SentenceTransformer(embedding_model)
    text = "Curiosity inspires creative, innovative communities worldwide."
    embedding = transformer.encode(text)
    print("\n===", embedding_model, len(embedding))

    for query in [
        "How does curiosity inspire communities?",
        "What's the best pet?",
        "What's the meaning of life?",
    ]:
        query_embedding = transformer.encode(query)
        # Code adapted from https://huggingface.co/sentence-transformers/multi-qa-mpnet-base-cos-v1
        score = util.dot_score(query_embedding, embedding)[0]
        print("Score:", score, "for:", query)
