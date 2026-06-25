"""Executable entrypoints and repository-tooling tests."""
from __future__ import annotations

import pytest

import read_file_and_list as context_dump
import run_smoke
import tools.gen_map as gen_map
import ui.server as ui_server


@pytest.mark.audit
@pytest.mark.integration
def test_deterministic_smoke_entrypoint_runs_without_network(capsys):
    assert run_smoke.main() == 0
    output = capsys.readouterr().out
    assert output.startswith("CORE_AGENT_SMOKE_OK run_id=")


@pytest.mark.audit
def test_ui_cli_main_honors_host_port_and_closes_resources(monkeypatch, capsys):
    observed = {}

    class Controller:
        def __init__(self):
            observed["controller"] = self
            self.closed = False

        def close(self):
            self.closed = True

    class Server:
        def __init__(self, address, controller):
            observed["address"] = address
            observed["server_controller"] = controller
            self.closed = False

        def serve_forever(self, *, poll_interval):
            observed["poll_interval"] = poll_interval
            raise KeyboardInterrupt

        def server_close(self):
            self.closed = True

    monkeypatch.setattr(ui_server, "RunController", Controller)
    monkeypatch.setattr(ui_server, "AgentUIServer", Server)

    assert ui_server.main(["--host", "0.0.0.0", "--port", "9876"]) == 0

    assert observed["address"] == ("0.0.0.0", 9876)
    assert observed["poll_interval"] == 0.25
    assert observed["controller"].closed is True
    assert capsys.readouterr().out == "Core Agent UI: http://0.0.0.0:9876\n"


@pytest.mark.audit
def test_ui_cli_rejects_non_integer_port():
    with pytest.raises(SystemExit) as error:
        ui_server.main(["--port", "not-an-integer"])
    assert error.value.code == 2


@pytest.mark.audit
def test_map_generator_handles_valid_missing_and_syntax_error_modules(tmp_path, monkeypatch, capsys):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    good = package / "good.py"
    good.write_text('"""First line.\nMore."""\n', encoding="utf-8")
    missing = package / "missing.py"
    missing.write_text("value = 1\n", encoding="utf-8")
    broken = package / "broken.py"
    broken.write_text("def broken(:\n", encoding="utf-8")
    monkeypatch.setattr(gen_map, "ROOT", tmp_path)

    assert gen_map.first_doc(good) == "First line."
    assert "module docstring" in gen_map.first_doc(missing)
    assert gen_map.first_doc(broken).startswith("(parse error:")
    assert gen_map.main() == 0

    generated = (tmp_path / "MAP.md").read_text(encoding="utf-8")
    assert "## pkg/" in generated
    assert "`pkg/good.py` | First line." in generated
    assert "`pkg/broken.py` | (parse error:" in generated
    assert capsys.readouterr().out == f"wrote {tmp_path / 'MAP.md'}\n"


@pytest.mark.audit
def test_context_dump_filters_secrets_binaries_and_large_files(tmp_path, monkeypatch, capsys):
    (tmp_path / ".env").write_text("SECRET=x", encoding="utf-8")
    (tmp_path / "visible.py").write_text("print('ok')", encoding="utf-8")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01")
    (tmp_path / "unknown.xyz").write_text("unknown", encoding="utf-8")
    large = tmp_path / "large.txt"
    large.write_bytes(b"x" * 2048)
    output = tmp_path / "project_context.txt"
    monkeypatch.setattr(context_dump, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(context_dump, "OUTPUT_FILE", output)
    monkeypatch.setattr(context_dump, "MAX_FILE_SIZE_MB", 0.001)

    assert context_dump.should_exclude_path(tmp_path / ".env") is True
    assert context_dump.should_exclude_path(tmp_path / "blob.bin") is True
    assert context_dump.safe_read_text(tmp_path / "unknown.xyz") == "[SKIPPED: not recognized as text file]"
    assert context_dump.safe_read_text(large).startswith("[SKIPPED: file too large")
    assert [path.name for path in context_dump.collect_files(tmp_path)] == ["large.txt", "unknown.xyz", "visible.py"]

    context_dump.main()
    generated = output.read_text(encoding="utf-8")
    assert "visible.py" in generated and "print('ok')" in generated
    assert ".env" not in generated and "blob.bin" not in generated
    assert "[SKIPPED: not recognized as text file]" in generated
    assert "Done. Project context saved to:" in capsys.readouterr().out
