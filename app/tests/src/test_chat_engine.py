from src import chat_engine
from src.chat_engine import GuruMultiprogramEngine, GuruSnapEngine


def test_available_engines():
    engines = chat_engine.available_engines()
    assert isinstance(engines, list)
    assert len(engines) > 0
    assert "guru-multiprogram" in engines
    assert "guru-snap" in engines
    assert "policy-mi" in engines


def test_create_engine_Guru_Multiprogram():
    engine_id = "guru-multiprogram"
    engine = chat_engine.create_engine(engine_id)
    assert engine is not None
    assert engine.name == GuruMultiprogramEngine.name


def test_create_engine_Guru_SNAP():
    engine_id = "guru-snap"
    engine = chat_engine.create_engine(engine_id)
    assert engine is not None
    assert engine.name == GuruSnapEngine.name
