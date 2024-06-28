import os
from src.generate import PROMPT, generate, get_models
from tests.mock import mock_completion
from tests.src.db.models.factories import ChunkFactory


def test_get_models(monkeypatch):
    if "OPENAI_API_KEY" in os.environ:
        monkeypatch.delenv("OPENAI_API_KEY")
    assert get_models() == {}

    monkeypatch.setenv("OPENAI_API_KEY", "mock_key")
    assert get_models() == {"OpenAI GPT-4o": "gpt-4o"}


def test_generate(monkeypatch):
    monkeypatch.setattr("src.generate.completion", mock_completion.mock_completion)
    expected_response = (
        'Called gpt-4o with [{"content": "'
        + PROMPT
        + '", "role": "system"}, {"content": "some query", "role": "user"}]'
    )
    assert generate("some query") == expected_response


def test_generate_with_context(monkeypatch):
    monkeypatch.setattr("src.generate.completion", mock_completion.mock_completion)
    context = [ChunkFactory.build(), ChunkFactory.build()]
    context_text = f"{context[0].document.name}\n{context[0].content}\n\n{context[1].document.name}\n{context[1].content}"
    expected_response = (
        'Called gpt-4o with [{"content": "'
        + PROMPT
        + '", "role": "system"}, {"content": "Use the following context to answer the question: '
        + context_text
        + '", "role": "system"}, {"content": "some query", "role": "user"}]'
    )
    assert generate("some query", context=context) == expected_response
