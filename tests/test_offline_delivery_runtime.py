from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_customer_launchers_prefer_bundled_runtime() -> None:
    launch = (ROOT / "启动AI投研.command").read_text(encoding="utf-8")
    initialize = (ROOT / "初始化环境.command").read_text(encoding="utf-8")

    for script in (launch, initialize):
        assert 'runtime/python/bin/python3' in script
        assert 'runtime/site-packages' in script
        assert 'PYTHONNOUSERSITE=1' in script
        assert 'SSL_CERT_FILE' in script

    assert launch.index('if [[ -x "$BUNDLED_PYTHON"') < launch.index('elif [[ -x "$ROOT_DIR/.venv/bin/python"')
    assert "无需安装 Python" in initialize


def test_runtime_directory_is_not_committed() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/runtime/" in gitignore
