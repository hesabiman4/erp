# Release, installation and recovery management

Open **Operations & planning → Release, installation and recovery** (`?view=runtime_management`). The page requires `settings.manage` and `runtime.manage`, complete location scope and complete product-line scope. An owner with `*` retains access; existing users receive no new permission automatically.

This is a read-only operator workspace. It cannot run a shell, migrate a database, apply an installation, change backup destinations, stop services or restore data. It shows actual release/dependency checks, PostgreSQL/schema state, maintenance freshness, deferred/configured backup metadata and evidence bound to the current database. It never displays passwords, connection strings, backup paths, financial totals or restored database names.

## Build and seal a reviewed release

From the repository directory, after all source and PDF edits stop:

```powershell
.venv/Scripts/python.exe scripts/build_release.py
.venv/Scripts/python.exe scripts/release_check.py --database --ledger
```

`build_release.py` hashes application inputs, runs the existing TypeScript/Vite build, and hashes the inputs again. A failed build or concurrent source change produces no new seal. The private `.local/releases/current.json` records the release identity, application version, source and built-asset checksums, and build date; an immutable-by-convention release-ID copy is retained beside it. The manifest does not contain secrets. Later source, manual PDF or built-asset changes make the displayed release state **changed**. Missing/unrecognized manifests remain **not sealed / invalid**, never silently verified. Rebuild/reseal after final changes. Running `npm build` separately after sealing requires another seal.

Checksums prove agreement with the recorded local build, not publisher authenticity. Signed distribution packages, automatic downloads and a Windows MSI installer are not implemented. The existing `scripts/install_runtime.ps1` remains a reviewable current-user startup-task installer, dry-run by default. No startup task was applied by this increment.

The pinned Python requirements are compared with installed package metadata. Source and asset fingerprints include the exact frontend lockfile; the successful existing frontend build verifies usable installed frontend tools. The PostgreSQL/schema check uses reads only. `--ledger` independently verifies balanced posted journals, inventory-control/pool agreement, pool cache/movement conservation, nonnegative stock and physical reservations without assuming a demo username. It is explicitly a core-integrity check, not full statutory or foreign-monetary-subledger certification; retain the existing broader accountant reconciliation routine.

## Review and apply a local update

First review the dry run against the configured application database:

```powershell
.venv/Scripts/python.exe scripts/update_release.py --database sponge_erp
```

This executes no backup, migration or update. It reports exact readiness, pending migrations and whether reviewed runtime ports are listening. A blocked dry run exits nonzero. The tool only accepts a named application database at loopback PostgreSQL port **55432** matching the configuration; system/remote/mismatched targets fail. No arbitrary shell command or automatic package download is accepted.

When an operator has reviewed the result, stopped the application and confirmed the target, the explicit local apply command is:

```powershell
.venv/Scripts/python.exe scripts/update_release.py --database sponge_erp --apply --confirm-database sponge_erp
```

The tool refuses listening ports (defaults 8080 and 8000; pass every reviewed app port with repeated `--port` values if deployment differs). It never kills a process. A PostgreSQL advisory lock prevents two concurrent update wrappers. It requires the stable sealed release and exact installed dependencies, then runs:

1. An encrypted PostgreSQL/private-attachment snapshot using the existing backup tool. A failed child or missing/empty snapshot blocks migration.
2. Forward Django migrations against the configured target.
3. Django checks.
4. The core ledger/schema/release checks above.

Private `.local/updates` reports/logs retain each outcome and the target database fingerprint. A failed step stops subsequent work, preserves the snapshot and report, and never restores over the active database. Migrations are **not** automatically rolled back; the snapshot is for separately reviewed recovery into a fresh copy. The operator restarts the runtime and verifies its health after a successful apply. The script is a guarded local forward-update workflow, not unattended production deployment. The guarded apply passed on a fresh restored copy and then the active local development database after snapshots; both are same-machine local verification, not a production rollout.

## Recovery evidence belongs to its actual source

New encrypted backup manifests include a fingerprint of the source host/port/database. A completed `scripts/recovery_check.py` copies this fingerprint from the restored manifest into its private report. It does not infer the source from the current app configuration or trust a matching restored-database name.

The workspace includes only recovery reports whose source fingerprint matches the current database and whose recorded successful stages contain restore, snapshot/private-attachment verification and ledger checks. Older reports without provenance remain preserved but are not displayed as proof for the current database. A mere `verified: true` without required steps is not accepted. Off-device recovery always remains **unverified** in this same-machine workflow. A fresh, successful restore drill supplies the evidence; the page never fabricates one.

Reports are local operator evidence, not signed independent attestations. A privileged filesystem/database administrator can change local evidence; the app does not claim to defend against that authority.

## Deferred configuration and limits

The owner chose **configure the backup destination later**. This release preserves that preference. Opening the workspace or running a dry run never configures a destination, sends a message, installs a logon task, publishes a server or connects an external service. Missing worker evidence is **not verified**, stale worker data is not labelled running, and a successful backup alone does not establish off-device recovery.

Native deployment acceptance, independently reviewed production security, off-device recovery and installation/update execution on a separate supported Windows machine remain operator rollout work. Tests exercise guards/failure handling with controlled child-process doubles and PostgreSQL read-only metadata; those tests do not claim a live production upgrade was performed.
