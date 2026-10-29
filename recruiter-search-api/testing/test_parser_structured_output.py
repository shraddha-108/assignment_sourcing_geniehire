from app.search import parser
from app.search.schema import ParsedQuery


def test_query_parser_uses_function_calling_for_parsed_query_schema(monkeypatch):
    calls = {}

    class FakeStructuredRunnable:
        def invoke(self, messages):
            calls["messages"] = messages
            return ParsedQuery()

    class FakeLLM:
        def with_structured_output(self, schema, **kwargs):
            calls["schema"] = schema
            calls["kwargs"] = kwargs
            return FakeStructuredRunnable()

    monkeypatch.setattr(parser, "_create_llm", lambda: FakeLLM())

    result = parser.parse_query("Python developer")

    assert isinstance(result, ParsedQuery)
    assert calls["schema"] is ParsedQuery
    assert calls["kwargs"]["method"] == "function_calling"
