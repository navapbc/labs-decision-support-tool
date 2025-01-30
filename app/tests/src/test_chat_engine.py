from src import chat_engine
from src.chat_engine import CaEddWebEngine, ImagineLA_MessageAttributes, ImagineLaEngine


def test_available_engines():
    engines = chat_engine.available_engines()
    assert isinstance(engines, list)
    assert len(engines) > 0
    assert "ca-edd-web" in engines
    assert "imagine-la" in engines


def test_create_engine_CA_EDD():
    engine_id = "ca-edd-web"
    engine = chat_engine.create_engine(engine_id)
    assert engine is not None
    assert engine.name == CaEddWebEngine.name
    assert engine.datasets == ["CA EDD"]


def test_create_engine_Imagine_LA():
    engine_id = "imagine-la"
    engine = chat_engine.create_engine(engine_id)
    assert engine is not None
    assert engine.name == ImagineLaEngine.name
    assert engine.datasets == [
        "CA EDD",
        "Imagine LA",
        "DPSS Policy",
        "IRS",
        "Keep Your Benefits",
        "CA FTB",
        "WIC",
        "Covered California",
    ]


def test_on_message_Imagine_LA_canned_response(monkeypatch):
    def mock_analyze_message(llm: str, system_prompt: str, message: str, response_format):
        return ImagineLA_MessageAttributes(
            needs_context=True,
            translated_message="",
            canned_response="This is a canned response",
            alert_message="",
        )

    monkeypatch.setattr(chat_engine, "analyze_message", mock_analyze_message)

    engine = chat_engine.create_engine("imagine-la")
    result = engine.on_message("What is AI?")
    assert result.response == "This is a canned response"
    assert result.attributes.alert_message == ""


def test_on_message_Imagine_LA_alert_message(monkeypatch):
    def mock_analyze_message(llm: str, system_prompt: str, message: str, response_format):
        return ImagineLA_MessageAttributes(
            needs_context=True,
            translated_message="",
            canned_response="",
            alert_message="Some alert message",
        )

    monkeypatch.setattr(chat_engine, "analyze_message", mock_analyze_message)

    def mock_generate(
        llm: str,
        system_prompt: str,
        query: str,
        context_text=None,
        chat_history=None,
    ) -> str:
        return "This is a generated response"

    monkeypatch.setattr(chat_engine, "generate", mock_generate)

    def mock_retrieve_with_scores(
        query: str,
        retrieval_k: int,
        retrieval_k_min_score: float,
        **filters,
    ):
        return []

    monkeypatch.setattr(chat_engine, "retrieve_with_scores", mock_retrieve_with_scores)

    engine = chat_engine.create_engine("imagine-la")
    result = engine.on_message("What is AI?")
    assert result.attributes.alert_message.startswith("**Policy update**: ")
    assert result.attributes.alert_message.endswith("\n\nThe rest of this answer may be outdated.")


def test_on_message_Imagine_LA_needs_context_False(monkeypatch):
    def mock_analyze_message(llm: str, system_prompt: str, message: str, response_format):
        return ImagineLA_MessageAttributes(
            needs_context=False,
            translated_message="",
            canned_response="",
            alert_message="Some alert message",
        )

    monkeypatch.setattr(chat_engine, "analyze_message", mock_analyze_message)

    def mock_generate(
        llm: str,
        system_prompt: str,
        query: str,
        context_text=None,
        chat_history=None,
    ) -> str:
        return "This is a generated response"

    monkeypatch.setattr(chat_engine, "generate", mock_generate)

    engine = chat_engine.create_engine("imagine-la")
    result = engine.on_message("What is AI?")
    assert result.attributes.alert_message.startswith("**Policy update**: ")
    assert result.attributes.alert_message.endswith("\n\nThe rest of this answer may be outdated.")
