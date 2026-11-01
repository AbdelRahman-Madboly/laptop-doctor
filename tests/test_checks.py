"""Checks fed with canned command output, so the result does not depend on this machine."""

from collections import namedtuple

import pytest

from laptop_doctor import checks
from laptop_doctor.util import human, uptime_text


def fake_run(outputs):
    """A stand-in for util.run that answers by the first argument that matches a key."""
    def run(args, *a, **k):
        text = " ".join(args) if isinstance(args, list) else args
        for key, out in outputs.items():
            if key in text:
                return out
        return ""
    return run


@pytest.mark.parametrize("pct,status", [(50, checks.OK), (85, checks.WARN), (93, checks.FAIL)])
def test_disk_thresholds(monkeypatch, pct, status):
    Usage = namedtuple("Usage", "total used free percent")
    monkeypatch.setattr(checks.psutil, "disk_usage", lambda _: Usage(100, pct, 10 * 2**30, pct))
    c = checks.check_disk()
    assert c.status == status and f"{pct}% used" in c.message and "10G free" in c.message
    assert (c.fix == "laptop clean") == (status != checks.OK)


def test_units_ok_when_nothing_failed(monkeypatch):
    monkeypatch.setattr(checks, "run", fake_run({}))
    assert checks.check_units().status == checks.OK


def test_units_ignore_terminal_scopes(monkeypatch):
    monkeypatch.setattr(checks, "run", fake_run({"--user": "vte-spawn-1234.scope loaded failed failed"}))
    assert checks.check_units().status == checks.OK


def test_stale_mounts_are_only_a_warning(monkeypatch):
    monkeypatch.setattr(checks, "run", fake_run({"--user": "", "--failed": "media-usb.mount loaded failed failed"}))
    c = checks.check_units()
    assert c.status == checks.WARN and "media-usb.mount" in c.message


def test_a_failed_service_is_a_failure(monkeypatch):
    monkeypatch.setattr(checks, "run", fake_run({
        "--user": "app.service loaded failed failed",
        "--failed": "cups.service loaded failed failed",
    }))
    c = checks.check_units()
    assert c.status == checks.FAIL
    assert "app.service" in c.message


def test_journal_errors_are_counted_by_program(monkeypatch):
    line = "Oct 26 10:00:00 host gnome-shell[123]: something broke"
    many = "\n".join([line] * (checks.ERRORS_WARN + 1))
    usb = "\n".join(["usb 1-1: device descriptor read/64, error -71"] * 11)
    monkeypatch.setattr(checks, "run", fake_run({"-k": usb, "journalctl": many}))
    c = checks.check_errors()
    assert c.status == checks.WARN
    assert f"gnome-shell({checks.ERRORS_WARN + 1})" in c.message
    assert "11 USB enumeration errors" in c.message


def test_few_journal_errors_are_fine(monkeypatch):
    monkeypatch.setattr(checks, "run", fake_run({}))
    c = checks.check_errors()
    assert c.status == checks.OK and "top: none" in c.message


@pytest.mark.parametrize("result,last,status", [
    ("success", "Sat 2026-11-01 03:00:00", checks.OK),
    ("exit-code", "Sat 2026-11-01 03:00:00", checks.FAIL),
    ("", "", checks.WARN),
])
def test_backups(monkeypatch, result, last, status):
    monkeypatch.setattr(checks, "run", fake_run({"-p Result": result, "ExecMainExitTimestamp": last}))
    assert checks.check_backups().status == status


def test_known_ports_file_is_parsed(tmp_path, monkeypatch):
    (tmp_path / "known-ports").write_text("# comment\n8765  phone app\n\n22 ssh\nnot-a-port\n")
    monkeypatch.setattr(checks, "REPO", tmp_path)
    assert checks.known_ports() == {8765, 22}


def test_ipv6_wildcard_listeners_count_as_exposed(monkeypatch):
    monkeypatch.setattr(checks, "run", lambda *a, **k: "LISTEN 0 4096 [::]:5432 [::]:*\nLISTEN 0 5 127.0.0.1:631 0.0.0.0:*")
    monkeypatch.setattr(checks, "known_ports", lambda: set())
    assert checks.exposed_ports() == [5432]
    assert checks.check_network().status == checks.WARN


def test_pending_updates_counts_apt_and_snap(monkeypatch):
    apt = "Listing...\na/noble 2 amd64 [upgradable from: 1]\nb/noble 2 amd64 [upgradable from: 1]"
    snap = "Name Version Rev\nfirefox 1 2\ncode 3 4"
    monkeypatch.setattr(checks, "run", fake_run({"apt": apt, "snap": snap}))
    assert checks.pending_updates() == (2, 2)
    monkeypatch.setattr(checks, "run", fake_run({"apt": "", "snap": "All snaps up to date."}))
    assert checks.pending_updates() == (0, 0)


def test_many_apt_updates_warn(monkeypatch):
    monkeypatch.setattr(checks, "pending_updates", lambda: (checks.APT_WARN + 1, 0))
    assert checks.check_updates().status == checks.WARN


def test_hot_cpu_warns(monkeypatch):
    monkeypatch.setattr(checks, "cpu_package_temp", lambda: float(checks.TEMP_WARN))
    assert checks.check_temps().status == checks.WARN
    monkeypatch.setattr(checks, "cpu_package_temp", lambda: None)
    assert checks.check_temps() is None


def test_battery_health_warns_below_threshold(monkeypatch):
    info = {"health": checks.BATTERY_WARN - 1, "cycles": "300", "status": "Discharging", "capacity": 60}
    monkeypatch.setattr(checks, "battery_info", lambda: info)
    c = checks.check_battery()
    assert c.status == checks.WARN and "300 cycles" in c.message
    monkeypatch.setattr(checks, "battery_info", lambda: {})
    assert checks.check_battery() is None


def test_unit_formatting_edges():
    assert human(0) == "0 B"
    assert human(1023) == "1023 B"
    assert human(1536) == "1.5 KB"
    assert human(5 * 1024**5) == "5120.0 TB"
    assert uptime_text(59) == "0m"
    assert uptime_text(3600) == "1h 0m"
    assert uptime_text(86400 + 61) == "1d 0h 1m"
