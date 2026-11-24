from django.db import migrations

SQL='''
CREATE TRIGGER ledger_immutable BEFORE INSERT OR UPDATE OR DELETE ON erp_collectionnote FOR EACH ROW EXECUTE FUNCTION erp_guard_ledger_row();
CREATE TRIGGER ledger_immutable BEFORE INSERT OR UPDATE OR DELETE ON erp_workproduction FOR EACH ROW EXECUTE FUNCTION erp_guard_ledger_row();
CREATE TRIGGER source_immutable BEFORE UPDATE OR DELETE ON erp_jobcard FOR EACH ROW EXECUTE FUNCTION erp_guard_source_record();
CREATE TRIGGER source_immutable BEFORE UPDATE OR DELETE ON erp_qualityinspection FOR EACH ROW EXECUTE FUNCTION erp_guard_source_record();
CREATE FUNCTION erp_guard_fx_wallet_dimensions() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.currency,NEW.kind,NEW.location_id,NEW.source_id) IS DISTINCT FROM (OLD.currency,OLD.kind,OLD.location_id,OLD.source_id) THEN
   RAISE EXCEPTION 'Currency wallet dimensions cannot change after creation';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER wallet_dimensions BEFORE UPDATE ON erp_foreignwallet FOR EACH ROW EXECUTE FUNCTION erp_guard_fx_wallet_dimensions();
CREATE FUNCTION erp_guard_remittance_dimensions() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.source_wallet_id,NEW.destination_wallet_id,NEW.foreign_amount,NEW.carrying_amount,NEW.source_id) IS DISTINCT FROM (OLD.source_wallet_id,OLD.destination_wallet_id,OLD.foreign_amount,OLD.carrying_amount,OLD.source_id) THEN
   RAISE EXCEPTION 'Remittance financial dimensions cannot change';
 END IF;
 IF OLD.completed_by_id IS NOT NULL AND NEW.completed_by_id IS DISTINCT FROM OLD.completed_by_id THEN
   RAISE EXCEPTION 'A received remittance cannot be reopened';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER remittance_dimensions BEFORE UPDATE ON erp_remittance FOR EACH ROW EXECUTE FUNCTION erp_guard_remittance_dimensions();
'''

class Migration(migrations.Migration):
    dependencies=[('erp','0011_foreign_guards_and_accounts')]
    operations=[migrations.RunSQL(SQL)]
