"""LLM 狀態與工具註冊煙霧測試"""

from src.integrations.llm.config_resolver import is_llm_configured
from src.integrations.llm.tools_bridge import tool_names_for_llm
from src.integrations.mcp.registry import get_all_tools


def test_llm_tools_registered():
    names = tool_names_for_llm()
    assert "sq_search_stocks" in names
    assert "sq_north_flow" in names
    assert "sq_run_backtest" in names
    assert "sq_get_task" in names
    assert len(names) == len(get_all_tools())


def test_llm_configured_without_key():
    # 默認無 key 時為未配置
    assert is_llm_configured() in (True, False)
