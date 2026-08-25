import pytest

from civilservant.llm import LlmError, validate_api_base


def test_api_base_accepts_https_and_local_http() -> None:
    assert validate_api_base("https://api.deepseek.com/") == "https://api.deepseek.com"
    assert validate_api_base("http://localhost:11434/") == "http://localhost:11434"


def test_api_base_rejects_remote_plain_http() -> None:
    with pytest.raises(LlmError):
        validate_api_base("http://example.com")

