import time

from laptop_doctor import checks, triage

KERNEL = """\
Oct 26 16:04:20 host kernel: gnome-shell invoked oom-killer: gfp_mask=0x140cca(GFP_HIGHUSER_MOVABLE|__GFP_COMP), order=0, oom_score_adj=100
Oct 26 16:04:20 host kernel: [   2892]   106  2892     3190       29       27        2         0    69632       94             0 kerneloops
Oct 26 16:04:20 host kernel: oom-kill:constraint=CONSTRAINT_NONE,nodemask=(null),cpuset=user.slice,mems_allowed=0,global_oom,task_memcg=/user.slice/user-1000.slice/user@1000.service/app.slice/app-org.gnome.Terminal.slice/vte-spawn-641f.scope,task=python3,pid=3213214,uid=1000
Oct 26 16:04:20 host kernel: Out of memory: Killed process 3213214 (python3) total-vm:22221164kB, anon-rss:11248336kB, file-rss:8kB, shmem-rss:0kB, UID:1000 pgtables:37876kB oom_score_adj:200
Oct 26 04:53:27 host kernel: oom-kill:constraint=CONSTRAINT_NONE,nodemask=(null),cpuset=user.slice,mems_allowed=0,global_oom,task_memcg=/user.slice/user-1000.slice/user@1000.service/app.slice/app-gnome-google\\x2dchrome-11369.scope,task=chrome,pid=1484433,uid=1000
Oct 26 04:53:27 host kernel: Out of memory: Killed process 1484433 (chrome) total-vm:1518837764kB, anon-rss:11292kB, file-rss:8kB, shmem-rss:600kB, UID:1000 pgtables:3568kB oom_score_adj:300
Oct 26 03:30:47 host kernel: oom-kill:constraint=CONSTRAINT_NONE,nodemask=(null),cpuset=docker-36a1.scope,mems_allowed=0,global_oom,task_memcg=/user.slice/user-1000.slice/user@1000.service/app.slice/app-org.gnome.Terminal.slice/vte-spawn-2782.scope,task=next-server (v1,pid=1655039,uid=1000
Oct 26 03:30:47 host kernel: Out of memory: Killed process 1655039 (next-server (v1) total-vm:69375116kB, anon-rss:4098080kB, file-rss:148kB, shmem-rss:0kB, UID:1000 pgtables:100392kB oom_score_adj:200
"""


def test_oom_kills_are_read_with_name_size_and_origin():
    kills = checks.oom_kills(KERNEL)
    assert [k.name for k in kills] == ["python3", "chrome", "next-server (v1"]
    assert kills[0].rss == 11248336 * 1024
    assert [k.origin for k in kills] == ["terminal", "Chrome", "terminal"]
    assert kills[0].when == "Oct 26 16:04"


def test_oom_summary_names_the_biggest_first():
    text = checks.oom_summary(checks.oom_kills(KERNEL))
    assert text.startswith("python3 10.7G")
    assert "next-server (v1 3.9G" in text


def test_kernel_section_drops_oom_noise_and_kerneloops():
    lines = triage.kernel_problems(KERNEL + "Oct 26 05:00:00 host kernel: NVRM: Xid (PCI:0000:01:00): 79\n")
    assert lines == ["Oct 26 05:00:00 host kernel: NVRM: Xid (PCI:0000:01:00): 79"]


def test_boots_ignore_logins(monkeypatch):
    seen = {}

    def fake_run(args, **kw):
        seen["args"] = args
        return "reboot   system boot  7.0.0 Fri Oct 23 16:46   still running\n\nwtmp begins Fri Jun 12"

    monkeypatch.setattr(triage, "run", fake_run)
    assert triage.boots() == ["reboot   system boot  7.0.0 Fri Oct 23 16:46   still running"]
    assert "reboot" in seen["args"] and "shutdown" in seen["args"]


def test_memory_is_summed_per_app():
    procs = [(2 * 2**30, "chrome"), (1 * 2**30, "chrome"), (2 * 2**30, "python3"), (2**20, "bash")]
    assert checks.group_by_app(procs, 2) == [(3 * 2**30, "chrome", 2), (2 * 2**30, "python3", 1)]


def test_memory_fix_only_mentions_gradle_when_daemons_run(monkeypatch):
    monkeypatch.setattr(checks.cleanup, "gradle_daemons", lambda: [])
    assert "Gradle" not in checks.memory_fix([(5 * 2**30, "chrome", 40)])
    assert "chrome" in checks.memory_fix([(5 * 2**30, "chrome", 40)])
    monkeypatch.setattr(checks.cleanup, "gradle_daemons", lambda: [object()])
    assert "Gradle" in checks.memory_fix([(5 * 2**30, "chrome", 40)])


def test_checks_run_side_by_side_and_keep_their_order(monkeypatch):
    def slow(name):
        def fn():
            time.sleep(0.3)
            return checks.Check(name, checks.OK, "m")
        return fn

    monkeypatch.setattr(checks, "ALL", [slow("a"), slow("b"), slow("c"), slow("d")])
    seen = []
    start = time.time()
    s = checks.run_all(progress=lambda done, total: seen.append((done, total)))
    assert time.time() - start < 0.9
    assert [c.name for c in s.checks] == ["a", "b", "c", "d"]
    assert seen[-1] == (4, 4) and len(seen) == 4


def test_a_background_task_is_released_on_the_gui_thread_after_delivering():
    from PySide6.QtCore import QCoreApplication, QThread

    from laptop_doctor.ui.widgets import Task, run_async

    app = QCoreApplication.instance() or QCoreApplication([])
    got = []
    run_async(lambda: QThread.currentThread(), on_done=got.append)
    assert len(Task._alive) == 1
    deadline = time.time() + 5
    while not got and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert got and got[0] is not app.thread()   # the work ran off the GUI thread
    assert not Task._alive                      # and was let go only once its result arrived
