"""Tests for the tool-usage reporting evaluator."""

from types import SimpleNamespace

from chat.evals.evaluators.tools_used import SourcesCount, ToolCalled, ToolNotCalled, ToolsUsed


def _ctx(tool_calls):
    return SimpleNamespace(output="answer", attributes={"tool_calls": tool_calls})


def test_tools_used_is_a_label_not_a_score():
    """The evaluator returns a string so it never changes pass/fail."""
    label = ToolsUsed().evaluate(_ctx([{"name": "document_search_rag", "args": {"query": "q"}}]))

    assert isinstance(label, str)
    assert label == "document_search_rag"


def test_tools_used_shows_summarize_instructions():
    """summarize calls expose the instructions the model handed over."""
    label = ToolsUsed().evaluate(
        _ctx([{"name": "summarize", "args": {"instructions": "tableau par thème"}}])
    )

    assert label == "summarize(instructions='tableau par thème')"


def test_tools_used_without_calls():
    """No tool call, or no attribute at all, reads as 'none'."""
    assert ToolsUsed().evaluate(_ctx([])) == "none"
    assert ToolsUsed().evaluate(SimpleNamespace(output="a", attributes={})) == "none"


def test_tool_called_passes_when_the_scored_turn_called_it():
    """ToolCalled reads the scored turn's tool calls."""
    assert ToolCalled(name="web_search").evaluate(_ctx([{"name": "web_search"}])).value is True


def test_tool_called_fails_without_call():
    """No such call fails, naming the tools that were called."""
    result = ToolCalled(name="web_search").evaluate(_ctx([{"name": "summarize"}]))

    assert result.value is False
    assert "summarize" in result.reason


def test_tool_not_called_fails_when_called():
    """ToolNotCalled is the opposite check (over-use of a tool)."""
    assert ToolNotCalled(name="web_search").evaluate(_ctx([{"name": "web_search"}])).value is False
    assert ToolNotCalled(name="web_search").evaluate(_ctx([])).value is True


def test_sources_count_reads_streamed_sources():
    """SourcesCount counts distinct streamed source URLs (UI chips), not text URLs."""
    ctx = SimpleNamespace(
        output="no url", attributes={"sources": ["https://a", "https://a", "https://b"]}
    )

    assert SourcesCount(minimum=2).evaluate(ctx).value is True
    assert SourcesCount(minimum=3).evaluate(ctx).value is False
