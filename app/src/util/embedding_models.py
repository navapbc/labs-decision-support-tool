from sentence_transformers import SentenceTransformer, util


def test_sentence_transformer(embedding_model: str) -> None:
    """
    Exercises specified embedding model and calculates scores from the embedding vectors.
    The embedding models will be downloaded automatically to ~/.cache/huggingface/hub, if it does not already exist.
    Used the scores to confirm/compare against those of pgvector's max_inner_product.
    """
    transformer = SentenceTransformer(embedding_model)
    # transformer.save(f"sentence_transformers/{embedding_model}")
    text = "Curiosity inspires creative, innovative communities worldwide."
    embedding = transformer.encode(text)
    print("=== ", embedding_model, len(embedding))

    for query in [
        text,
        "How does curiosity inspire communities?",
        "What's the best pet?",
        "What's the meaning of life?",
    ]:
        query_embedding = transformer.encode(query)
        # Code adapted from https://huggingface.co/sentence-transformers/multi-qa-mpnet-base-cos-v1
        score = util.dot_score(embedding, query_embedding)
        print("Score:", score.item(), "for:", query)


# To run: python -m src.util.embedding_models
if __name__ == "__main__":
    embedding_models = ["multi-qa-mpnet-base-cos-v1", "multi-qa-mpnet-base-dot-v1"]
    for model in embedding_models:
        print(model)
        test_sentence_transformer(model)
