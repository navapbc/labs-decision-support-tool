from src import chat_engine
from src.chat_engine import CaEddWebEngine, ImagineLaEngine


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
    ]
