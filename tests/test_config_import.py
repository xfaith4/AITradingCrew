"""A1: configuration and crew modules import without API keys; LLMs are lazy."""
import pytest


def test_config_imports_without_credentials(run_python):
    result = run_python(
        "import ai_trading_crew.config as c; print(','.join(c.settings.SYMBOLS))"
    )
    assert result.returncode == 0, result.stderr
    assert "AAPL" in result.stdout


def test_crew_module_imports_without_credentials(run_python):
    result = run_python("import ai_trading_crew.crew; print('ok')")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("ok")


def test_get_llm_without_credentials_raises(no_credentials):
    from ai_trading_crew import config

    config.get_llm.cache_clear()
    with pytest.raises(EnvironmentError, match="OPENROUTER_API_KEY"):
        config.get_llm("PROJECT_LLM")


def test_get_llm_is_cached_per_name(monkeypatch):
    from ai_trading_crew import config

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_DEEPSEEK_R1", "openrouter/deepseek/deepseek-r1")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.example/api/v1")
    config.get_llm.cache_clear()
    try:
        first = config.get_llm("PROJECT_LLM")
        assert config.get_llm("PROJECT_LLM") is first
        assert config.get_llm("DEFAULT_TI_LLM") is not first
        # Legacy attribute access still resolves through the factory.
        assert config.PROJECT_LLM is first
    finally:
        config.get_llm.cache_clear()


def test_get_llm_rejects_unknown_name():
    from ai_trading_crew import config

    with pytest.raises(ValueError, match="Unknown LLM name"):
        config.get_llm("NOT_A_MODEL")
