import src.chat_engine as chat_engine
from src.chat_engine import GuruMultiprogramEngine, GuruSnapEngine, OnMessageResult


def test_available_engines():
    engines = chat_engine.available_engines()
    assert isinstance(engines, list)
    assert len(engines) > 0
    assert "guru-multiprogram" in engines
    assert "guru-snap" in engines
    assert "policy-mi" in engines


def create_on_message_result(response="Some LLM response", chunks=None):
    return OnMessageResult(response, chunks or [])


def test_create_engine_Guru_Multiprogram():
    engine_id = "guru-multiprogram"
    engine = chat_engine.create_engine(engine_id)
    assert engine is not None
    assert engine.name == GuruMultiprogramEngine.name
    engine.on_start()

    assert engine.format_answer_message(create_on_message_result()).startswith("Some LLM response")


def test_create_engine_Guru_SNAP():
    engine_id = "guru-snap"
    engine = chat_engine.create_engine(engine_id)
    assert engine is not None
    assert engine.name == GuruSnapEngine.name
    engine.on_start()

    assert engine.format_answer_message(create_on_message_result()).startswith("Some LLM response")
