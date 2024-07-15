import os
import sys

from src.generate import PROMPT, generate, get_models
from tests.mock import mock_completion
from tests.src.db.models.factories import ChunkFactory


def test_get_models(monkeypatch):
    if "OPENAI_API_KEY" in os.environ:
        monkeypatch.delenv("OPENAI_API_KEY")
    if "OLLAMA_HOST" in os.environ:
        monkeypatch.delenv("OLLAMA_HOST")
    assert get_models() == {}

    monkeypatch.setenv("OPENAI_API_KEY", "mock_key")
    assert get_models() == {"OpenAI GPT-4o": "gpt-4o"}


def test_get_models_ollama(monkeypatch):
    if "OPENAI_API_KEY" in os.environ:
        monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("OLLAMA_HOST", "mock_key")
    monkeypatch.setattr(ollama, "list", ollama_model_list)
    #sys.modules["ollama"] = __import__("mock_ollama")
    # TODO: use `monkeypatch_module` so that sys.modules doesn't mess up other tests
    assert get_models() == {
        "Ollama llama3:latest": "ollama/llama3:latest",
        "Ollama dolphin-mistral:latest": "ollama/dolphin-mistral:latest",
        "Ollama openhermes:latest": "ollama/openhermes:latest",
        "Ollama llama2:latest": "ollama/llama2:latest",
    }


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
