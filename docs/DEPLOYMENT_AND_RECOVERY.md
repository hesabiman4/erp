# Deployment and recovery

## Current authorized environment

Native local development only, with loopback-bound PostgreSQL/API/frontend. No public hosting, external accounts, paid services, or real business data have been used. The Compose file is an alternative development setup; Docker was unavailable during initial native testing.

## Configuration

Start with .env.example and generate unique secrets. Development convenience defaults must not reach public deployment. Production requires DEBUG=0, explicit host/origin allowlists, HTTPS termination, secure session/CSRF cookies, a maintained WSGI/ASGI server, and monitored PostgreSQL with least-privilege application credentials. Do not use the local development database superuser or Django runserver in production.

Separate migration ownership from application database privileges. PostgreSQL guards protect normal application changes, not a database superuser who can disable triggers. Private media must never be exposed as public static content. Serve downloads only through authorized endpoints.

## Recovery protocol

1. Run scripts/backup.py backup. It holds a read-only repeatable snapshot while pg_dump exports the database and captures the attachment manifest. Attachments are immutable files, and the snapshot includes only referenced files.
2. Store the encrypted archive off-server. Retain its Fernet key separately, plus secure configuration/application-secret references. The generated key is not a substitute for managed backup key custody.
3. Restore into a new local restore_* database and separate storage. The helper refuses overwriting the configured live database or an existing target.
4. Verify document count, stock value, journal balance, and attachment checksums; then verify application login and scoped attachment retrieval against the restored database.
5. For an actual disaster recovery event, an authorized operator must plan live cutover and operational reconciliation; this local restore helper never switches live users automatically.

The current helper builds its encrypted archive in memory; large databases require a reviewed streaming/envelope-encryption backup process. Document measured restore time and data volume before agreeing recovery time/recovery point objectives.

## Go-live gates

- Validate actual tax, withholding, legal entity, calendar, wages, opening balances, inventory value, and accounting/cost allocation with the business accountant.
- Review every role and location/product-line permission with the owner. Enable TOTP for finance/owner accounts and test recovery procedures.
- Review language translations with native Dari/Pashto users. Confirm invoice/printer output at the required sizes.
- Resolve incomplete requirements listed in implementation status; do not treat a hidden or unavailable workflow as implemented.
- Test complete purchase→production→trim→sale→collection→transfer→payroll→close journeys using representative data and reconciled controls.
- Run security review, dependency audit, production configuration checks, load measurements, backup/restore rehearsal, monitored error reporting, and migration rollback planning.
- Train cashiers/storekeepers and agree cash/stock closing, discrepancy approval, period locks, and backup ownership.
