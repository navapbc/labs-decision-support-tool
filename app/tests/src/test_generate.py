import os

import ollama

from src.generate import PROMPT, generate, get_models
from tests.mock import mock_completion
from tests.src.db.models.factories import ChunkFactory


def ollama_model_list():
    return {
        "models": [
            {
                "name": "llama3:latest",
                "model": "llama3:latest",
                "modified_at": "2024-07-08T11:17:37.56309816-04:00",
                "size": 4661224676,
                "digest": "365c0bd3c000a25d28ddbf732fe1c6add414de7275464c4e4d1c3b5fcb5d8ad1",
                "details": {
                    "parent_model": "",
                    "format": "gguf",
                    "family": "llama",
                    "families": ["llama"],
                    "parameter_size": "8.0B",
                    "quantization_level": "Q4_0",
                },
            },
            {
                "name": "dolphin-mistral:latest",
                "model": "dolphin-mistral:latest",
                "modified_at": "2024-05-02T11:32:07.462296027-04:00",
                "size": 4108940323,
                "digest": "5dc8c5a2be6510dcb2afbcffdedc73acbd5868d2c25d9402f6044beade3d5f70",
                "details": {
                    "parent_model": "",
                    "format": "gguf",
                    "family": "llama",
                    "families": ["llama"],
                    "parameter_size": "7B",
                    "quantization_level": "Q4_0",
                },
            },
            {
                "name": "openhermes:latest",
                "model": "openhermes:latest",
                "modified_at": "2024-03-06T18:23:02.98963318-05:00",
                "size": 4108928574,
                "digest": "95477a2659b7539758230498d6ea9f6bfa5aa51ffb3dea9f37c91cacbac459c1",
                "details": {
                    "parent_model": "",
                    "format": "gguf",
                    "family": "llama",
                    "families": ["llama"],
                    "parameter_size": "7B",
                    "quantization_level": "Q4_0",
                },
            },
            {
                "name": "llama2:latest",
                "model": "llama2:latest",
                "modified_at": "2024-02-08T13:30:36.981193992-05:00",
                "size": 3826793677,
                "digest": "78e26419b4469263f75331927a00a0284ef6544c1975b826b15abdaef17bb962",
                "details": {
                    "parent_model": "",
                    "format": "gguf",
                    "family": "llama",
                    "families": ["llama"],
                    "parameter_size": "7B",
                    "quantization_level": "Q4_0",
                },
            },
        ]
    }


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
