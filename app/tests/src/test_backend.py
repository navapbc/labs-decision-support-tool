from src.backend import get_retrieval_metadata


def test_get_retrieval_metadata(chunks_with_scores):
    assert get_retrieval_metadata(chunks_with_scores) == {
        "chunks": [
            {
                "document.name": chunks_with_scores[0].chunk.document.name,
                "chunk.id": str(chunks_with_scores[0].chunk.id),
                "score": chunks_with_scores[0].score,
            },
            {
                "document.name": chunks_with_scores[1].chunk.document.name,
                "chunk.id": str(chunks_with_scores[1].chunk.id),
                "score": chunks_with_scores[1].score,
            },
            {
                "document.name": chunks_with_scores[2].chunk.document.name,
                "chunk.id": str(chunks_with_scores[2].chunk.id),
                "score": chunks_with_scores[2].score,
            },
        ]
    }
