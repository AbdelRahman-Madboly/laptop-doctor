import json

import pytest

from laptop_doctor import checks, cleanup, cli, report, triage
from laptop_doctor.util import human, uptime_text


def test_every_check_returns_a_known_status():
    s = checks.run_all()
    assert s.checks, "no checks ran"
    for c in s.checks:
        assert c.status in (checks.OK, checks.WARN, checks.FAIL), c
        assert c.message
        assert c.title
    assert 0 <= s.score <= 100
    assert s.status == (checks.FAIL if s.fails else checks.WARN if s.warns else checks.OK)


def test_a_crashing_check_becomes_a_warning(monkeypatch):
    def boom():
        raise RuntimeError("sensor gone")
    monkeypatch.setattr(checks, "ALL", [boom, checks.check_disk])
    s = checks.run_all()
    assert s.checks[0].status == checks.WARN and "sensor gone" in s.checks[0].message
    assert s.checks[1].name == "disk"


@pytest.mark.parametrize("warns,fails,score", [(0, 0, 100), (1, 0, 94), (0, 1, 82), (6, 6, 0)])
def test_score(warns, fails, score):
    s = checks.Summary([checks.Check("x", checks.WARN, "m")] * warns + [checks.Check("y", checks.FAIL, "m")] * fails)
    assert s.score == score


def test_gpu_mismatch_is_a_failure_with_reboot_fix(monkeypatch):
    monkeypatch.setattr(checks, "have", lambda _: True)
    monkeypatch.setattr(checks, "run", lambda *a, **k: "Failed to initialize NVML: Driver/library version mismatch")
    c = checks.check_gpu()
    assert c.status == checks.FAIL and c.fix == "reboot"


def test_known_ports_are_not_reported(monkeypatch):
    monkeypatch.setattr(checks, "run", lambda *a, **k: "LISTEN 0 4096 0.0.0.0:8765 0.0.0.0:*\nLISTEN 0 5 0.0.0.0:22 0.0.0.0:*")
    monkeypatch.setattr(checks, "known_ports", lambda: {8765})
    assert checks.exposed_ports() == [22]


def test_cleanup_scan_lists_all_three_kinds():
    items = cleanup.scan()
    kinds = {i.kind for i in items}
    assert cleanup.SAFE in kinds and cleanup.SUDO in kinds
    for i in items:
        if i.kind == cleanup.SUDO:
            assert i.command.startswith(("sudo", "snap"))


def test_apply_with_no_keys_only_reports_disk():
    log = cleanup.apply([])
    assert len(log) == 1 and log[0].startswith("disk now")


def test_history_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "HISTORY", tmp_path / "h.jsonl")
    s = checks.Summary([checks.Check("disk", checks.WARN, "m")])
    report.record(s)
    report.record(s)
    rows = report.history()
    assert len(rows) == 2 and rows[0]["score"] == 94 and rows[0]["checks"] == {"disk": "WARN"}
    json.dumps(rows)


def test_report_written_and_pruned(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "REPORTS", tmp_path)
    monkeypatch.setattr(report, "HISTORY", tmp_path / "h.jsonl")
    monkeypatch.setattr(triage, "crashes", lambda days: [("Boots", ["reboot x"])])
    for i in range(report.KEEP + 3):
        (tmp_path / f"2020-01-{i:02d}.md").write_text("old")
    path = report.write(checks.Summary([checks.Check("disk", checks.OK, "fine")]))
    text = path.read_text()
    assert "OK    disk" in text and "## Boots" in text
    assert len(list(tmp_path.glob("*.md"))) == report.KEEP


def test_cli_usage_and_unknown_command(capsys):
    assert cli.main(["help"]) == 0
    assert "laptop <command>" in capsys.readouterr().out
    assert cli.main(["nope"]) == 64


def test_formatting():
    assert human(512) == "512 B"
    assert human(1536) == "1.5 KB"
    assert uptime_text(90061) == "1d 1h 1m"
