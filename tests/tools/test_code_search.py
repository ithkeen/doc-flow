"""code_search 工具测试。"""

import json

from src.config import settings
from src.tools.code_search import find_function


class TestFindFunction:
    def test_finds_plain_function(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        go_dir = tmp_path / "service"
        go_dir.mkdir()
        (go_dir / "buy.go").write_text(
            "package service\n\nfunc buyResourcePostPaid(ctx context.Context) error {\n\treturn nil\n}\n"
        )

        result = json.loads(find_function.invoke({"function_name": "buyResourcePostPaid", "directory": "service"}))
        assert result["success"] is True
        assert result["payload"]["file"].endswith("service/buy.go")
        assert result["payload"]["line"] == 3
        assert "buyResourcePostPaid" in result["payload"]["content"]
