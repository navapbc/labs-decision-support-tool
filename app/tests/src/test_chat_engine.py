from src import chat_engine
from src.app_config import app_config
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

    # Check that the engine has the same configuration value as the app_config
    assert engine.user_config.retrieval_k == app_config.retrieval_k


class TestChatEngine(ChatEngineInterface):
    engine_id: str = "test_chat_engine"
    name: str = "Test Chat Engine for unit tests"
    datasets = ["guru-snap", "guru-multiprogram", "policy-mi"]

    def __init__(self) -> None:
        super().__init__()
        self.user_config = app_config.create_user_config()
        # Set a default retrieval_k
        self.user_config.retrieval_k = 2
        # Remove the retrieval_k_min_score configuration for an engine
        self.user_config.__delattr__("retrieval_k_min_score")

    def on_message(self, question: str) -> OnMessageResult:
        self._testing_hook(question)
        return OnMessageResult("Some generated response from LLM", [])

    def _testing_hook(self, question: str):
        print("====\n====", question)
        return


def test_user_config_initialization():
    engine = chat_engine.create_engine("test_chat_engine")
    assert engine is not None
    assert engine.datasets == TestChatEngine.datasets

    assert engine.user_config.retrieval_k == 2
    assert not hasattr(engine.user_config, "retrieval_k_min_score")


def test_user_config_change(monkeypatch):
    engine = chat_engine.create_engine("test_chat_engine")

    # Simulate user changing the configuration value
    engine.user_config.retrieval_k = 5  # similar code as in chainlit.py

    # Check that the engine has the new configuration value
    def assert_new_config_used(self, _question):
        assert self.user_config.retrieval_k == 5

    monkeypatch.setattr(TestChatEngine, "_testing_hook", assert_new_config_used)
    engine.on_message("A test question")
