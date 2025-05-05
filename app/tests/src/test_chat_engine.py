import pytest

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
        "Benefits Information Hub",
        "DPSS Policy",
        "IRS",
        "Keep Your Benefits",
        "CA FTB",
        "WIC",
        "Covered California",
        "SSA",
    ]


def test_on_message_Imagine_LA_canned_response(monkeypatch):
    monkeypatch.setattr(
        chat_engine,
        "analyze_message",
        lambda *_, **_kw: ImagineLA_MessageAttributes(
            needs_context=True,
            users_language="en",
            translated_message="",
            benefit_program="",
            canned_response="This is a canned response",
            alert_message="",
        ),
    )

    engine = chat_engine.create_engine("imagine-la")
    result = engine.on_message("What is AI?")
    assert result.response == "This is a canned response"
    assert not result.attributes.benefit_program
    assert not result.attributes.alert_message


def test_on_message_Imagine_LA_alert_message(monkeypatch):
    monkeypatch.setattr(
        chat_engine,
        "analyze_message",
        lambda *_, **_kw: ImagineLA_MessageAttributes(
            needs_context=True,
            users_language="en",
            translated_message="",
            benefit_program="CalFresh",
            canned_response="",
            alert_message="Some alert message",
        ),
    )
    monkeypatch.setattr(chat_engine, "generate", lambda *_, **_kw: "This is a generated response")
    monkeypatch.setattr(chat_engine, "retrieve_with_scores", lambda *_, **_kw: [])

    engine = chat_engine.create_engine("imagine-la")
    result = engine.on_message("What is AI?")
    assert result.response == "This is a generated response"
    assert result.attributes.benefit_program == "CalFresh"
    assert result.attributes.alert_message == "Some alert message"


def test_on_message_Imagine_LA_needs_context_False(monkeypatch):
    monkeypatch.setattr(
        chat_engine,
        "analyze_message",
        lambda *_, **_kw: ImagineLA_MessageAttributes(
            needs_context=False,
            users_language="en",
            translated_message="",
            benefit_program="CalFresh",
            canned_response="",
            alert_message="Some alert message",
        ),
    )
    monkeypatch.setattr(chat_engine, "generate", lambda *_, **_kw: "This is a generated response")

    engine = chat_engine.create_engine("imagine-la")
    result = engine.on_message("What is AI?")
    assert result.response == "This is a generated response"
    assert not result.chunks_with_scores
    assert not result.subsections
    assert result.attributes.benefit_program == "CalFresh"
    assert result.attributes.alert_message == "Some alert message"


@pytest.mark.asyncio
async def test_on_message_streaming_Imagine_LA_canned_response(monkeypatch):
    monkeypatch.setattr(
        chat_engine,
        "analyze_message",
        lambda *_, **_kw: ImagineLA_MessageAttributes(
            needs_context=True,
            users_language="en",
            translated_message="",
            benefit_program="",
            canned_response="This is a canned response",
            alert_message="",
        ),
    )

    engine = chat_engine.create_engine("imagine-la")
    generator, attributes, subsections = await engine.on_message_streaming("What is AI?")

    # For canned responses, we should get the exact response in a single chunk
    chunks = []
    async for chunk in generator:
        chunks.append(chunk)

    assert chunks == ["This is a canned response"]
    assert not attributes.benefit_program
    assert not attributes.alert_message
    assert not subsections


@pytest.mark.asyncio
async def test_on_message_streaming_Imagine_LA_with_context(monkeypatch):
    monkeypatch.setattr(
        chat_engine,
        "analyze_message",
        lambda *_, **_kw: ImagineLA_MessageAttributes(
            needs_context=True,
            users_language="en",
            translated_message="",
            benefit_program="CalFresh",
            canned_response="",
            alert_message="Some alert message",
        ),
    )

    # Mock the streaming generator to return known chunks
    async def mock_generate_streaming(*args, **kwargs):
        chunks = ["First chunk", " second chunk", " final chunk"]
        for chunk in chunks:
            yield chunk

    monkeypatch.setattr(chat_engine, "generate_streaming_async", mock_generate_streaming)
    # Mock retrieval to return empty results (but still exercise the code path)
    monkeypatch.setattr(chat_engine, "retrieve_with_scores", lambda *_, **_kw: [])

    engine = chat_engine.create_engine("imagine-la")
    generator, attributes, subsections = await engine.on_message_streaming("What is AI?")

    # Collect and verify streamed chunks
    chunks = []
    async for chunk in generator:
        chunks.append(chunk)

    assert chunks == ["First chunk", " second chunk", " final chunk"]
    assert attributes.benefit_program == "CalFresh"
    assert attributes.alert_message == "Some alert message"
    assert subsections == []  # Empty because we mocked retrieve_with_scores to return []
