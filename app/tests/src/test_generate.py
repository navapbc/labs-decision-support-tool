from src.generate import generate, get_models
from tests.mock import mock_completion


def test_get_models(monkeypatch):
    assert get_models() == {}

    monkeypatch.setenv("OPENAI_API_KEY", "mock_key")
    assert get_models() == {"OpenAI GPT-4o": "gpt-4o"}


def test_generate(monkeypatch):
    monkeypatch.setattr("src.generate.completion", mock_completion.mock_completion)
    expected_response = 'Called gpt-4o with [{"content": "Provide answers in plain language written at the average American reading level. \\n            Use bullet points. Keep your answers brief, max of 5 sentences. \\n            Keep your answers as similar to your knowledge text as you can", "role": "system"}, {"content": "some_string", "role": "user"}]'
    assert generate("some_string") == expected_response
