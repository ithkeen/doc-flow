"""LogSettings 单元测试。"""

from src.config.settings import LogSettings, Settings


class TestLogSettings:
    """LogSettings 配置测试。"""

    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.delenv("LOG_DIR", raising=False)
        monkeypatch.delenv("LOG_BACKUP_COUNT", raising=False)

        s = LogSettings(_env_file=None)
        assert s.level == "INFO"
        assert s.dir == "logs/"
        assert s.backup_count == 7

    def test_loads_from_env(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("LOG_DIR", "/var/log/docflow/")
        monkeypatch.setenv("LOG_BACKUP_COUNT", "14")

        s = LogSettings(_env_file=None)
        assert s.level == "DEBUG"
        assert s.dir == "/var/log/docflow/"
        assert s.backup_count == 14

    def test_settings_includes_log(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        s = Settings(_env_file=None)
        assert s.log.level == "INFO"
        assert s.log.dir == "logs/"
        assert s.log.backup_count == 7
