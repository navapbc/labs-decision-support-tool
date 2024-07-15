import src.chat_engine as chat_engine
from src.chat_engine import GuruMultiprogramEngine, GuruSnapEngine


def test_available_engines():
    engines = chat_engine.available_engines()
    assert isinstance(engines, list)
    assert len(engines) > 0
    assert "guru-multiprogram" in engines
    assert "guru-snap" in engines
    assert "policy-mi" in engines


async def test_create_engine_Guru_Multiprogram():
    engine_id = "guru-multiprogram"
    engine = chat_engine.create_engine(engine_id)
    assert engine is not None
    assert engine.name == GuruMultiprogramEngine.name
    settings = await engine.on_start()
    assert settings["use_guru_snap_dataset"] is False
    assert settings["use_guru_multiprogram_dataset"] is True

    assert engine.format_answer_message({}) == ""


async def test_create_engine_Guru_SNAP():
    engine_id = "guru-snap"
    engine = chat_engine.create_engine(engine_id)
    assert engine is not None
    assert engine.name == GuruSnapEngine.name
    settings = await engine.on_start()
    assert settings["use_guru_snap_dataset"] is True
    assert settings["use_guru_multiprogram_dataset"] is False

    assert engine.format_answer_message({}) == ""
