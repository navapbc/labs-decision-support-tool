from src.generate import get_models


def test_get_models(monkeypatch):
    assert get_models() == {}

    monkeypatch.setenv("OPENAI_API_KEY", "mock_key")
    assert get_models() == {"OpenAI GPT-4o": "gpt-4o"}
