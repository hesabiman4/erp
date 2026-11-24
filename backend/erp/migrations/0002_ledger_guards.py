from django.db import migrations

SQL = r'''
CREATE OR REPLACE FUNCTION erp_guard_business() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE biz bigint; related_biz bigint; fk record; record_json jsonb;
BEGIN
  record_json := to_jsonb(NEW);
  biz := (record_json->>'business_id')::bigint;
  IF biz IS NULL AND record_json ? 'document_id' THEN
    SELECT business_id INTO biz FROM erp_document WHERE id=(record_json->>'document_id')::bigint;
  END IF;
  FOR fk IN
    SELECT a.attname AS col, c.confrelid AS parent_oid, c.confrelid::regclass AS parent_table
    FROM pg_constraint c
    JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=c.conkey[1]
    WHERE c.contype='f' AND c.conrelid=TG_RELID
  LOOP
    IF record_json->>fk.col IS NOT NULL AND EXISTS(SELECT 1 FROM pg_attribute WHERE attrelid=fk.parent_oid AND attname='business_id' AND NOT attisdropped) THEN
      EXECUTE format('SELECT business_id FROM %s WHERE id=$1',fk.parent_table) INTO related_biz USING (record_json->>fk.col)::bigint;
      IF related_biz IS DISTINCT FROM biz THEN RAISE EXCEPTION 'Cross-business reference rejected on %',TG_TABLE_NAME; END IF;
    END IF;
  END LOOP;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION erp_guard_immutable_document() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.state='posted' THEN RAISE EXCEPTION 'Posted documents are immutable; use a linked correction'; END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $$;

CREATE OR REPLACE FUNCTION erp_guard_ledger_row() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE doc_id bigint; doc_state text;
BEGIN
  IF TG_OP='INSERT' THEN doc_id=NEW.document_id; ELSE doc_id=OLD.document_id; END IF;
  SELECT state INTO doc_state FROM erp_document WHERE id=doc_id;
  IF doc_state='posted' THEN RAISE EXCEPTION 'Posted ledger rows are append-only'; END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $$;

CREATE OR REPLACE FUNCTION erp_guard_balanced_document() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE difference numeric; inventory_gl numeric; inventory_stock numeric;
BEGIN
  IF NEW.state='posted' THEN
    SELECT COALESCE(sum(debit-credit),0) INTO difference FROM erp_entry WHERE document_id=NEW.id;
    IF difference<>0 THEN RAISE EXCEPTION 'Unbalanced journal rejected'; END IF;
    SELECT COALESCE(sum(e.debit-e.credit),0) INTO inventory_gl FROM erp_entry e JOIN erp_account a ON a.id=e.account_id WHERE e.document_id=NEW.id AND a.code IN ('RAW','FG','TRIM','TRANSIT');
    SELECT COALESCE(sum(value),0) INTO inventory_stock FROM erp_stockmovement WHERE document_id=NEW.id;
    IF round(inventory_gl,2)<>round(inventory_stock,2) THEN RAISE EXCEPTION 'Inventory value and control journal do not reconcile'; END IF;
  END IF;
  RETURN NEW;
END $$;

DO $$ DECLARE tab text; BEGIN
  FOREACH tab IN ARRAY ARRAY['location','warehouse','membership','product','party','account','employee','document','stockpool','block','stockmovement','entry','allocation','bom','asset','taxrule','auditevent','attachment'] LOOP
    EXECUTE format('CREATE TRIGGER business_scope BEFORE INSERT OR UPDATE ON erp_%I FOR EACH ROW EXECUTE FUNCTION erp_guard_business()',tab);
  END LOOP;
  FOREACH tab IN ARRAY ARRAY['entry','stockmovement','allocation'] LOOP
    EXECUTE format('CREATE TRIGGER ledger_immutable BEFORE INSERT OR UPDATE OR DELETE ON erp_%I FOR EACH ROW EXECUTE FUNCTION erp_guard_ledger_row()',tab);
  END LOOP;
END $$;
CREATE TRIGGER document_immutable BEFORE UPDATE OR DELETE ON erp_document FOR EACH ROW EXECUTE FUNCTION erp_guard_immutable_document();
CREATE TRIGGER document_balanced AFTER INSERT OR UPDATE OF state ON erp_document FOR EACH ROW EXECUTE FUNCTION erp_guard_balanced_document();
'''

REVERSE = r'''
DROP FUNCTION IF EXISTS erp_guard_balanced_document() CASCADE;
DROP FUNCTION IF EXISTS erp_guard_ledger_row() CASCADE;
DROP FUNCTION IF EXISTS erp_guard_immutable_document() CASCADE;
DROP FUNCTION IF EXISTS erp_guard_business() CASCADE;
'''

class Migration(migrations.Migration):
    dependencies=[('erp','0001_initial')]
    operations=[migrations.RunSQL(SQL,REVERSE)]
