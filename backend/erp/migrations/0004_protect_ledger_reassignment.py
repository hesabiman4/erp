from django.db import migrations

SQL=r'''
CREATE OR REPLACE FUNCTION erp_guard_ledger_row() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE doc_id bigint; doc_state text;
BEGIN
  IF TG_OP='INSERT' THEN doc_id=NEW.document_id; ELSE doc_id=OLD.document_id; END IF;
  SELECT state INTO doc_state FROM erp_document WHERE id=doc_id;
  IF doc_state='posted' THEN RAISE EXCEPTION 'Posted ledger rows are append-only'; END IF;
  IF TG_OP='UPDATE' AND NEW.document_id IS DISTINCT FROM OLD.document_id THEN
    SELECT state INTO doc_state FROM erp_document WHERE id=NEW.document_id;
    IF doc_state='posted' THEN RAISE EXCEPTION 'Cannot move ledger rows into a posted document'; END IF;
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $$;

CREATE OR REPLACE FUNCTION erp_guard_allocation_sign() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_kind text;
BEGIN
  SELECT kind INTO owner_kind FROM erp_document WHERE id=NEW.document_id;
  IF NEW.amount<0 AND owner_kind<>'payment_reverse' THEN
    RAISE EXCEPTION 'Negative allocation requires a linked payment reversal';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER allocation_sign BEFORE INSERT OR UPDATE ON erp_allocation FOR EACH ROW EXECUTE FUNCTION erp_guard_allocation_sign();
'''

class Migration(migrations.Migration):
    dependencies=[('erp','0003_compensating_payment_allocations')]
    operations=[migrations.RunSQL(SQL,'DROP FUNCTION IF EXISTS erp_guard_allocation_sign() CASCADE;')]
