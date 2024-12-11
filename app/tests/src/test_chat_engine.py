from src import chat_engine
from src.chat_engine import BridgesEligibilityManualEngine


def test_available_engines():
    engines = chat_engine.available_engines()
    assert isinstance(engines, list)
    assert len(engines) > 0
    assert "bridges-eligibility-manual" in engines


def test_create_engine_BridgesEligibilityManualEngine():
    engine_id = "bridges-eligibility-manual"
    engine = chat_engine.create_engine(engine_id)
    assert engine is not None
    assert engine.name == BridgesEligibilityManualEngine.name
