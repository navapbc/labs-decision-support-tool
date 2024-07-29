from src import chat_engine
from src.chat_engine import (
    ChatEngineInterface,
    GuruMultiprogramEngine,
    GuruSnapEngine,
    OnMessageResult,
)


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


class TestChatEngine(ChatEngineInterface):
    engine_id: str = "test_chat_engine"
    name: str = "Test Chat Engine for unit tests"
    datasets = ["guru-snap", "guru-multiprogram", "policy-mi"]

    # Engine-specific configurations
    retrieval_k = 2

    def on_message(self, question: str) -> OnMessageResult:
        self._testing_hook(question)
        return OnMessageResult("Some generated response from LLM", [])

    def _testing_hook(self, question: str):
        return


def test_user_config_initialization():
    engine = chat_engine.create_engine("test_chat_engine")
    assert engine is not None
    assert engine.datasets == TestChatEngine.datasets

    assert engine.retrieval_k == 2


def test_user_config_change(monkeypatch):
    engine = chat_engine.create_engine("test_chat_engine")

    # Simulate user changing the configuration value
    engine.retrieval_k = 5  # similar code as in chainlit.py

    # Check that the engine has the new configuration value
    def assert_new_config_used(self, question):
        assert self.retrieval_k == 5

    monkeypatch.setattr(TestChatEngine, "_testing_hook", assert_new_config_used)
    engine.on_message("A test question")
