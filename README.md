# Nawa — Manufacturing ERP

Dari-first manufacturing and accounting application for sponge sold by sheet-thickness cm, adhesive sold by kg, and isolated additional businesses. PostgreSQL is required. The authoritative scope is [ERP_AI_CODER_MASTER_PROMPT.md](ERP_AI_CODER_MASTER_PROMPT.md).

Owner pilot (2026-11-22, this local machine): use `Open Owner Training.cmd` and http://localhost:8081/ with its separate synthetic database/private generated logins. Main remains http://127.0.0.1:8080/. Follow the [Dari owner pilot guide](docs/OWNER_PILOT_GUIDE.md) and record actual observations in [the owner acceptance record](docs/OWNER_PILOT_RECORD.md). The local pilot helpers/media/credentials live under ignored `.local/pilots/owner_20261122/`; the root launcher alone is not a portable fresh installation. Do not distribute private credentials or seed the main books. Human/accountant/Android/iPhone/off-device acceptance remains pending.

The application includes Operations & planning, shared Jalali dates, AFN-functional foreign monetary workflows, customer portal, manufacturing controls, reviewed commissions, job/BOM planning and subcontract source tracking. Exact variants and limits are in [COMPETITIVE_ROADMAP.md](docs/COMPETITIVE_ROADMAP.md). Latest daily workflows: [task profiles, counter sales, guidance, CRM, local reviewed OCR, production board and full document pages](docs/DAILY_WORKFLOW_V5.md). Staff acceptance and native/accountant review remain separate from automated verification.

Latest daily controls: [tables, attention, structured drafts/undo, trends/timelines, shortcuts, separate banks/drawers and backup Settings](docs/DAILY_CONTROLS_V6.md). Illustrated accounting guides are available in Dari, English and Pashto from the accounts screen. These are verified local workflows; business-staff/native/accountant and off-device recovery acceptance remain separate.

English/Pashto interface and advanced-help coverage is documented in [LOCALIZATION.md](docs/LOCALIZATION.md). Dari remains the default; all21 learning steps now have Pashto explanations. Run `node scripts/check_localization.cjs` to check static resource coverage. Native editorial review and exhaustive runtime-error localization remain separate.

For the built single-origin local app, run `.venv/Scripts/python.exe scripts/build_release.py`, then `.venv/Scripts/python.exe scripts/run_runtime.py --port 8080` and open **http://127.0.0.1:8080/**. The builder records source/asset integrity after the TypeScript/Vite build. This supervisor starts the existing project-local PostgreSQL cluster if needed, serves built assets/API through Waitress and runs maintenance ticks. It never initializes/resets a database. Set `ERP_START_LOCAL_DB=0` when local cluster management is not wanted. `scripts/install_runtime.ps1` previews a current-user logon task; `-Apply` installs it. The current build has not installed that task automatically.

Choose the encrypted backup destination in **Business settings → Encrypted backups** from the host computer, using a locally provisioned host-operator account. The panel browses existing folders, tests write access, saves the interval and provides reviewed Back up now. The live destination stays **not_configured** until you choose it. `ERP_BACKUP_DIRECTORY` remains an operator fallback. See [daily controls](docs/DAILY_CONTROLS_V6.md) for the local provisioning command and recovery limits. Private manual snapshots continue to work. Gateway acceptance is not confirmed reminder delivery; real messaging configuration/authorization is separate. The development URLs below remain available.

## Local Windows setup

Prerequisites: Python 3.13, Node 22, PostgreSQL 18 binaries on PATH (the helper also detects the normal Windows PostgreSQL 18 installation). Commands below run from the project root. This is a local development build, not a public production deployment.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\local_db.py init
.\.venv\Scripts\python.exe backend\manage.py migrate
.\.venv\Scripts\python.exe backend\manage.py collectstatic --noinput
.\.venv\Scripts\python.exe backend\manage.py seed_demo --demo
npm --prefix frontend ci
```

The isolated development PostgreSQL cluster uses `127.0.0.1:55432`, database `sponge_erp`. It does not reuse or modify your system PostgreSQL service. Secrets are generated into ignored `.env.local`; synthetic role passwords are in ignored `.local/demo-credentials.json`. Open that file locally to obtain the `owner` password; passwords are not embedded in source code.

For an already installed instance, start all three local services with one command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local.ps1
```

This starts the existing project database and hidden development servers, verifies the web page and proxied database health, and writes logs under `.local`. It does not reset data or seed records. Run it again after restarting Windows or if the local URL stops responding. The URL works on this computer while these services are running.

Alternatively, start these in two terminals:

```powershell
.\.venv\Scripts\python.exe scripts\local_db.py start
.\.venv\Scripts\python.exe backend\manage.py runserver 127.0.0.1:8000
```

```powershell
npm --prefix frontend run dev
```

Open [the local ERP](http://127.0.0.1:5173/). The frontend proxies `/api/` to Django. Use `owner` for both demo businesses, `herat_cashier` or `kabul_cashier` for assigned sales, `factory` for production, `accountant` for finance, and `furniture` for the separate furniture business. All passwords are individually generated. Do not share this demo instance publicly.

`seed_demo --demo` is repeatable; it does not reset or overwrite existing transactions/passwords. No automatic reset command exists. Stop the two development servers with Ctrl+C. Stop only this project's PostgreSQL cluster with `scripts/local_db.py stop` after closing active application sessions.

## Verification

```powershell
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pytest --reuse-db
.\.venv\Scripts\python.exe scripts\reconcile.py
npm --prefix frontend run build
```

Run only one pytest process at a time against the shared default test database. Tests exercise real PostgreSQL transactions and triggers, including concurrent cuts, exact decimals, journal balancing, partial payments, production, transfers, isolation, and valuation. Browser and recovery evidence is recorded separately in `docs/VERIFICATION.md`; a planned test is not a passing test.

With both servers running, verify the synthetic browser journeys using the locally installed Microsoft Edge:

```powershell
Set-Location frontend
$env:ERP_DEMO_E2E='1'
npx playwright test
```

This explicit demo test posts synthetic sales, receipts, production, and transfers. It requires the generated local demo credentials and must not target real company data. Screenshots, printed PDFs, and the browser evidence summary are saved under `.local/browser`.

The interface redesign and its workflows are described in `docs/UX_REDESIGN.md`. The browser tests also accept `ERP_E2E_BASE_URL`, `ERP_E2E_CREDENTIALS` and `ERP_E2E_OUTPUT` for an independently seeded verification instance. Use a separate `verify_*` database and API/frontend ports when the active instance holds records you want to preserve. The 2026-10-29 transaction checks used this isolation. `usability.spec.ts` previews forms and reads data without posting business transactions.

## Backups and recovery

```powershell
.\.venv\Scripts\python.exe scripts\backup.py backup --output .local\backups\erp-snapshot.fernet
.\.venv\Scripts\python.exe scripts\backup.py restore --input .local\backups\erp-snapshot.fernet --database restore_verification
```

Backup uses a consistent PostgreSQL snapshot and private-attachment manifest, then encrypts the bundle. Keep the generated `.local/backup.key` in a separate secure location; without it the archive cannot be decrypted. Never commit keys or archives. Restore refuses existing/live database names and writes separate media under `.local/restores/restore_verification/media`. It verifies document counts, inventory value, journal balance, and attachment hashes.

To inspect a restored instance, set `PGDATABASE=restore_verification` and `PRIVATE_MEDIA_ROOT` to the restored media path in a separate process, and run Django on a different local port. Do not repoint the active instance while users are working.

## Administration and recovery

Create a Django superuser if maintenance access is required:

```powershell
.\.venv\Scripts\python.exe backend\manage.py createsuperuser
.\.venv\Scripts\python.exe backend\manage.py changepassword owner
```

Django's authentication superuser is not automatically an ERP business member. Assign ERP memberships through the existing owner/settings workflow. The authenticated user can configure TOTP MFA, change their password, or revoke sessions. After admin password recovery, revoke prior sessions as appropriate.

## Docker alternative

`compose.yaml` describes a local development database/API/frontend stack. Supply the environment values from `.env.example` with generated secrets, then run:

```powershell
docker compose --env-file .env.local up --build
docker compose --env-file .env.local exec api python manage.py migrate
docker compose --env-file .env.local exec api python manage.py seed_demo --demo
```

Docker execution must be verified separately; native Windows verification does not prove that the container setup ran. Docker ports bind to loopback. The Compose stack is development configuration and uses Django's development server.

## Accounting and operational boundaries

- Grade labels such as “45 کیلو گرام” are names, never automatic block mass.
- Cm balances apply only within matching sheet footprints. Blocks are physically tracked.
- Actual production requires no BOM; furniture demo demonstrates an optional approved BOM.
- Nonzero conversion labor/overhead must reference posted eligible costs, avoiding double-counted payroll or invented clearing balances.
- Internal branch charges do not create company external revenue, customer AR, or inventory markup.
- Posted records remain immutable. Use supported returns, reversals, and linked adjustments.
- Active inventory write-downs support sales/reversal; transformation/transfer of affected pools is blocked pending review.
- Foreign currency posting, partial-face cutting, historical cost replay, Jalali input, statutory intercompany consolidation, and unrestricted offline posting remain unavailable.
- Tax settings, legal reporting entity mapping, real opening balances, wage rules, cost allocation, deployment hardening, and operating procedures need owner/accountant review before real use.

See `docs/ARCHITECTURE.md`, `docs/ACCOUNTING_RULES.md`, `docs/USER_GUIDE.md`, `docs/IMPLEMENTATION_STATUS.md`, and `docs/HANDOFF.md` for the current implementation evidence and remaining work. Do not infer full production readiness from a successful build.
