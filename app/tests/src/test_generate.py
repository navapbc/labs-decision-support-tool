import os

import ollama
import pytest

from src.chat_engine import PROMPT
from src.citations import create_prompt_context, split_into_subsections
from src.generate import generate, generate_streaming_async, get_models
from tests.mock import mock_completion


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
    if "AWS_ACCESS_KEY_ID" in os.environ:
        monkeypatch.delenv("AWS_ACCESS_KEY_ID")
    if "OPENAI_API_KEY" in os.environ:
        monkeypatch.delenv("OPENAI_API_KEY")
    if "OLLAMA_HOST" in os.environ:
        monkeypatch.delenv("OLLAMA_HOST")
    assert get_models() == {}

    monkeypatch.setenv("OPENAI_API_KEY", "mock_key")
    assert get_models()["OpenAI GPT-4o"] == "gpt-4o"

    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock_key")
    assert get_models()["Anthropic Claude 3.5 Sonnet"] == "claude-3-5-sonnet-20240620"


def test_get_models_ollama(monkeypatch):
    if "OPENAI_API_KEY" in os.environ:
        monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("OLLAMA_HOST", "mock_key")
    monkeypatch.setattr(ollama, "list", ollama_model_list)

    ollama_models = {k: v for k, v in get_models().items() if v.startswith("ollama/")}
    assert ollama_models == {
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
    assert generate("gpt-4o", PROMPT, "some query") == expected_response


def test_generate_with_history(monkeypatch):
    monkeypatch.setattr("src.generate.completion", mock_completion.mock_completion)
    history = [
        {"content": "some query", "role": "user"},
        {"content": "<div> answer</div>", "role": "assistant"},
    ]
    expected_response = (
        'Called gpt-4o with [{"content": "' + PROMPT + '", "role": "system"}, '
        '{"content": "Use the following context to answer the question: context", "role": "system"}, '
        '{"content": "some query", "role": "user"}, '
        '{"content": "<div> answer</div>", "role": "assistant"}, '
        '{"content": "some other query", "role": "user"}]'
    )

    assert (
        generate(
            llm="gpt-4o",
            system_prompt=PROMPT,
            context_text="context",
            chat_history=history,
            query="some other query",
        )
        == expected_response
    )


def test_generate_with_context_with_score(monkeypatch, chunks_with_scores):
    monkeypatch.setattr("src.generate.completion", mock_completion.mock_completion)
    subsection = split_into_subsections([c.chunk for c in chunks_with_scores])
    context_text = create_prompt_context(subsection)
    expected_response = (
        'Called gpt-4o with [{"content": "'
        + PROMPT
        + '", "role": "system"}, {"content": "Use the following context to answer the question: '
        + context_text
        + '", "role": "system"}, {"content": "some query", "role": "user"}]'
    )
    assert generate("gpt-4o", PROMPT, "some query", context_text) == expected_response


@pytest.mark.asyncio
async def test_generate_streaming_async(monkeypatch):
    monkeypatch.setattr("src.generate.completion", mock_completion.mock_completion)

    # Collect the streamed chunks
    result = []
    async for piece in generate_streaming_async(
        llm="gpt-4o",
        system_prompt=PROMPT,
        query="some query",
        context_text="context",
        chat_history=[{"role": "user", "content": "hi"}],
    ):
        result.append(piece)

    # Join chunks to verify complete response matches expected format
    complete_response = "".join(result)
    expected_response = (
        'Called gpt-4o with [{"content": "'
        + PROMPT
        + '", "role": "system"}, '
        + '{"content": "Use the following context to answer the question: context", "role": "system"}, '
        + '{"content": "hi", "role": "user"}, '
        + '{"content": "some query", "role": "user"}]'
    )
    assert complete_response == expected_response
