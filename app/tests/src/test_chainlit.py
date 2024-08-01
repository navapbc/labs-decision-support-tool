from src import chainlit, chat_engine


def test_url_query_values():
    url = "https://example.com/?engine=guru-snap&llm=gpt-4o&retrieval_k=3&someunknownparam=42"
    query_values = chainlit.url_query_values(url)
    engine_id = query_values.pop("engine")
    assert engine_id == "guru-snap"

    engine = chat_engine.create_engine(engine_id)

    input_widgets: list[str] = [
        query_values.pop(setting_name, None) or getattr(engine, setting_name)
        for setting_name in engine.user_settings
        if setting_name in chainlit._WIDGET_FACTORIES
    ]

    assert len(input_widgets) == len(engine.user_settings)
    assert len(query_values) == 1
    assert query_values["someunknownparam"] == "42"
