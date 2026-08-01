import os
from pathlib import Path

from group_food_agent.config import load_project_dotenv


def test_project_dotenv_loads_when_process_value_is_missing(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROUP_FOOD_SKIP_DOTENV", raising=False)

    loaded = load_project_dotenv(env_file)

    assert loaded == env_file.resolve()
    assert os.environ["OPENAI_API_KEY"] == "from-file"


def test_project_dotenv_does_not_override_process_value(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "from-process")
    monkeypatch.delenv("GROUP_FOOD_SKIP_DOTENV", raising=False)

    load_project_dotenv(env_file)

    assert os.environ["OPENAI_API_KEY"] == "from-process"


def test_project_dotenv_can_be_disabled(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GROUP_FOOD_SKIP_DOTENV", "1")

    assert load_project_dotenv(env_file) is None
    assert "OPENAI_API_KEY" not in os.environ
