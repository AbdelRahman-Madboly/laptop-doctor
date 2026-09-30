# laptop-doctor

Health checks, crash triage, cleanup and update tracking for the Dell G15 5530 (Ubuntu 24.04).
Read-only by default. Root-level fixes are printed for you to run, never run automatically.

```
laptop check            one-screen OK/WARN/FAIL summary
laptop crashes [days]   boots, crash files, OOM kills, GPU Xid, lockups, previous-boot errors
laptop clean [--apply]  reclaimable space; --apply clears safe user caches and idle Gradle/Kotlin daemons
laptop updates          apt, snap, flatpak, toolchains, npm globals
laptop report [--notify] writes reports/YYYY-MM-DD.md (last 30 kept, not committed)
laptop snapshot         full software inventory (machine-notes/scan.sh)
```

`systemd/laptop-doctor.timer` (installed to `~/.config/systemd/user/`) runs `laptop report --notify`
at 09:30 and 5 minutes after login; a desktop notification appears when anything is WARN or FAIL.

The machine record (current state, numbered issues, changelog, reinstall playbook) lives in
`~/machine-notes/`.

`known-ports`: services that are meant to listen on all interfaces.
