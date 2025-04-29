from src.embeddings.mock import MockEmbeddingModel


def test_mock_embedding_model():
    """Test the mock embedding model interface."""
    model = MockEmbeddingModel()

    # Test properties
    assert isinstance(model.max_seq_length, int)
    assert model.max_seq_length > 0
    assert hasattr(model.tokenizer, "tokenize")

    # Test single string encoding
    single_text = "This is a test sentence."
    single_embedding = model.encode(single_text)
    assert isinstance(single_embedding, list)
    assert len(single_embedding) > 0
    assert all(isinstance(x, float) for x in single_embedding)

    # Test batch encoding
    texts = ["First sentence.", "Second longer sentence for testing."]
    embeddings = model.encode(texts)
    assert isinstance(embeddings, list)
    assert len(embeddings) == len(texts)
    assert all(isinstance(embedding, list) for embedding in embeddings)
    assert all(all(isinstance(x, float) for x in embedding) for embedding in embeddings)

    # Test deterministic behavior
    text1 = "short"
    text2 = "a much longer piece of text with many words"

    emb1 = model.encode(text1)
    emb2 = model.encode(text2)

    # Check that embeddings are different
    assert emb1 != emb2

    # Check deterministic behavior - same text should always produce same embedding
    assert model.encode(text1) == emb1
    assert model.encode(text2) == emb2
