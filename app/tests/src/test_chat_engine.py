from src import chat_engine
from src.chat_engine import CaEddWebEngine, ImagineLaEngine
from src.generate import MessageAttributes
from tests.mock import mock_completion


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
    assert engine.datasets == ["CA EDD", "Imagine LA"]


def test_build_response(monkeypatch, caplog):
    new_eng = CaEddWebEngine()
    message = MessageAttributes(
        original_language="spanish",
        is_in_english=False,
        needs_context=False,
    )

    monkeypatch.setattr(
        "src.generate.completion",
        mock_completion.mock_completion("gpt-4o", ""),
    )

    new_eng._build_response_with_context("what is ssi?", message)
    logger_message = caplog.records[-1]
    assert (
        "Message_in_english was omitted even though a translation was expected"
        in logger_message.message
    )
