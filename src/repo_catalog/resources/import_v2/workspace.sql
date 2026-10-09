-- Import/finalization workspace only. Not part of the portable catalog.
-- All tables and triggers below stay within the attached workspace schema.
CREATE TABLE import_workspace_identity(
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    format_id TEXT NOT NULL CHECK(format_id='repo-catalog/import-workspace'),
    schema_version INTEGER NOT NULL CHECK(schema_version=2),
    target_db_instance_id TEXT NOT NULL,
    target_ddl_sha256 BLOB NOT NULL CHECK(length(target_ddl_sha256)=32),
    workspace_ddl_sha256 BLOB NOT NULL CHECK(length(workspace_ddl_sha256)=32)
) STRICT;
CREATE TRIGGER import_workspace_identity_immutable BEFORE UPDATE ON import_workspace_identity BEGIN SELECT RAISE(ABORT,'Immutable workspace binding'); END;
CREATE TRIGGER import_workspace_identity_retain BEFORE DELETE ON import_workspace_identity BEGIN SELECT RAISE(ABORT,'Retain workspace binding'); END;
CREATE TRIGGER import_workspace_identity_no_replace BEFORE INSERT ON import_workspace_identity WHEN EXISTS(SELECT 1 FROM import_workspace_identity) BEGIN SELECT RAISE(ABORT,'Workspace already bound'); END;
CREATE TABLE conversion_sources(
conversion_source_id TEXT PRIMARY KEY, source_sha256 BLOB NOT NULL CHECK(length(source_sha256)=32), schema_sha256 BLOB NOT NULL CHECK(length(schema_sha256)=32), format_id TEXT NOT NULL, source_db_instance_id TEXT NOT NULL, source_catalog BLOB NOT NULL, source_migrations BLOB NOT NULL
) STRICT;
CREATE TABLE conversion_runs(
conversion_run_id TEXT PRIMARY KEY, conversion_source_id TEXT NOT NULL REFERENCES conversion_sources(conversion_source_id) ON UPDATE RESTRICT ON DELETE RESTRICT, started_at_us INTEGER NOT NULL, ended_at_us INTEGER, parser_version TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('building','paused','validated','rejected')), manifest TEXT NOT NULL CHECK(json_valid(manifest) AND json_type(manifest)='object')
) STRICT;
CREATE TABLE conversion_batches(
conversion_batch_id INTEGER PRIMARY KEY, conversion_run_id TEXT NOT NULL REFERENCES conversion_runs(conversion_run_id) ON UPDATE RESTRICT ON DELETE RESTRICT, source_table TEXT NOT NULL, input_sha256 BLOB NOT NULL CHECK(length(input_sha256)=32), committed_at_us INTEGER NOT NULL, output_manifest TEXT NOT NULL CHECK(json_valid(output_manifest) AND json_type(output_manifest)='object')
) STRICT;
CREATE TABLE legacy_records(
legacy_record_id INTEGER PRIMARY KEY, conversion_source_id TEXT NOT NULL REFERENCES conversion_sources(conversion_source_id) ON UPDATE RESTRICT ON DELETE RESTRICT, source_table TEXT NOT NULL, source_key BLOB NOT NULL, row_sha256 BLOB NOT NULL CHECK(length(row_sha256)=32), UNIQUE(conversion_source_id,source_table,source_key)
) STRICT;
CREATE TABLE legacy_values(
legacy_record_id INTEGER NOT NULL REFERENCES legacy_records(legacy_record_id) ON UPDATE RESTRICT ON DELETE RESTRICT, column_name TEXT NOT NULL, storage_type TEXT NOT NULL CHECK(storage_type IN ('null','integer','real','text','blob')), value_bytes BLOB NOT NULL, PRIMARY KEY(legacy_record_id,column_name), CHECK(storage_type!='null' OR length(value_bytes)=0)
) STRICT;
CREATE TABLE id_mappings(
id_mapping_id INTEGER PRIMARY KEY, legacy_record_id INTEGER NOT NULL REFERENCES legacy_records(legacy_record_id) ON UPDATE RESTRICT ON DELETE RESTRICT, target_table TEXT NOT NULL, target_key BLOB NOT NULL, relation TEXT NOT NULL CHECK(relation IN ('identity','split','merge','derived','archive')), reason TEXT NOT NULL
) STRICT;
CREATE TABLE validation_results(
validation_result_id INTEGER PRIMARY KEY, conversion_run_id TEXT NOT NULL REFERENCES conversion_runs(conversion_run_id) ON UPDATE RESTRICT ON DELETE RESTRICT, invariant_id TEXT NOT NULL, code TEXT NOT NULL, severity TEXT NOT NULL CHECK(severity IN ('blocking','partial','info')), observed_at_us INTEGER NOT NULL, details TEXT NOT NULL CHECK(json_valid(details) AND json_type(details)='object')
) STRICT;
CREATE TABLE reanalysis_runs(
reanalysis_run_id TEXT PRIMARY KEY, conversion_run_id TEXT REFERENCES conversion_runs(conversion_run_id) ON UPDATE RESTRICT ON DELETE RESTRICT, parser_version TEXT NOT NULL, parsed_at_us INTEGER NOT NULL, evidence TEXT NOT NULL CHECK(json_valid(evidence) AND json_type(evidence)='object')
) STRICT;
CREATE TRIGGER conversion_batches_immutable BEFORE UPDATE ON conversion_batches WHEN NEW.conversion_batch_id IS NOT OLD.conversion_batch_id OR NEW.conversion_run_id IS NOT OLD.conversion_run_id OR NEW.source_table IS NOT OLD.source_table OR NEW.input_sha256 IS NOT OLD.input_sha256 OR NEW.committed_at_us IS NOT OLD.committed_at_us OR NEW.output_manifest IS NOT OLD.output_manifest BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER conversion_batches_no_replace BEFORE INSERT ON conversion_batches WHEN EXISTS(SELECT 1 FROM conversion_batches WHERE (conversion_batch_id=NEW.conversion_batch_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER conversion_batches_retain BEFORE DELETE ON conversion_batches BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX conversion_batches_fk_0 ON conversion_batches(conversion_run_id);
CREATE TRIGGER conversion_runs_immutable BEFORE UPDATE ON conversion_runs WHEN NEW.conversion_run_id IS NOT OLD.conversion_run_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER conversion_runs_no_replace BEFORE INSERT ON conversion_runs WHEN EXISTS(SELECT 1 FROM conversion_runs WHERE (conversion_run_id=NEW.conversion_run_id) OR (conversion_run_id=NEW.conversion_run_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX conversion_runs_fk_0 ON conversion_runs(conversion_source_id);
CREATE TRIGGER conversion_sources_immutable BEFORE UPDATE ON conversion_sources WHEN NEW.conversion_source_id IS NOT OLD.conversion_source_id OR NEW.source_sha256 IS NOT OLD.source_sha256 OR NEW.schema_sha256 IS NOT OLD.schema_sha256 OR NEW.format_id IS NOT OLD.format_id OR NEW.source_db_instance_id IS NOT OLD.source_db_instance_id OR NEW.source_catalog IS NOT OLD.source_catalog OR NEW.source_migrations IS NOT OLD.source_migrations BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER conversion_sources_no_replace BEFORE INSERT ON conversion_sources WHEN EXISTS(SELECT 1 FROM conversion_sources WHERE (conversion_source_id=NEW.conversion_source_id) OR (conversion_source_id=NEW.conversion_source_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER conversion_sources_retain BEFORE DELETE ON conversion_sources BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER id_mappings_immutable BEFORE UPDATE ON id_mappings WHEN NEW.id_mapping_id IS NOT OLD.id_mapping_id OR NEW.legacy_record_id IS NOT OLD.legacy_record_id OR NEW.target_table IS NOT OLD.target_table OR NEW.target_key IS NOT OLD.target_key OR NEW.relation IS NOT OLD.relation OR NEW.reason IS NOT OLD.reason BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER id_mappings_no_replace BEFORE INSERT ON id_mappings WHEN EXISTS(SELECT 1 FROM id_mappings WHERE (id_mapping_id=NEW.id_mapping_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER id_mappings_retain BEFORE DELETE ON id_mappings BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX id_mappings_fk_0 ON id_mappings(legacy_record_id);
CREATE TRIGGER legacy_records_immutable BEFORE UPDATE ON legacy_records WHEN NEW.legacy_record_id IS NOT OLD.legacy_record_id OR NEW.conversion_source_id IS NOT OLD.conversion_source_id OR NEW.source_table IS NOT OLD.source_table OR NEW.source_key IS NOT OLD.source_key OR NEW.row_sha256 IS NOT OLD.row_sha256 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER legacy_records_no_replace BEFORE INSERT ON legacy_records WHEN EXISTS(SELECT 1 FROM legacy_records WHERE (legacy_record_id=NEW.legacy_record_id) OR (conversion_source_id=NEW.conversion_source_id AND source_table=NEW.source_table AND source_key=NEW.source_key)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER legacy_records_retain BEFORE DELETE ON legacy_records BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER legacy_values_immutable BEFORE UPDATE ON legacy_values WHEN NEW.legacy_record_id IS NOT OLD.legacy_record_id OR NEW.column_name IS NOT OLD.column_name OR NEW.storage_type IS NOT OLD.storage_type OR NEW.value_bytes IS NOT OLD.value_bytes BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER legacy_values_no_replace BEFORE INSERT ON legacy_values WHEN EXISTS(SELECT 1 FROM legacy_values WHERE (legacy_record_id=NEW.legacy_record_id AND column_name=NEW.column_name) OR (legacy_record_id=NEW.legacy_record_id AND column_name=NEW.column_name)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER legacy_values_retain BEFORE DELETE ON legacy_values BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER reanalysis_runs_immutable BEFORE UPDATE ON reanalysis_runs WHEN NEW.reanalysis_run_id IS NOT OLD.reanalysis_run_id OR NEW.conversion_run_id IS NOT OLD.conversion_run_id OR NEW.parser_version IS NOT OLD.parser_version OR NEW.parsed_at_us IS NOT OLD.parsed_at_us OR NEW.evidence IS NOT OLD.evidence BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER reanalysis_runs_no_replace BEFORE INSERT ON reanalysis_runs WHEN EXISTS(SELECT 1 FROM reanalysis_runs WHERE (reanalysis_run_id=NEW.reanalysis_run_id) OR (reanalysis_run_id=NEW.reanalysis_run_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER reanalysis_runs_retain BEFORE DELETE ON reanalysis_runs BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX reanalysis_runs_fk_0 ON reanalysis_runs(conversion_run_id);
CREATE TRIGGER validation_results_immutable BEFORE UPDATE ON validation_results WHEN NEW.validation_result_id IS NOT OLD.validation_result_id OR NEW.conversion_run_id IS NOT OLD.conversion_run_id OR NEW.invariant_id IS NOT OLD.invariant_id OR NEW.code IS NOT OLD.code OR NEW.severity IS NOT OLD.severity OR NEW.observed_at_us IS NOT OLD.observed_at_us OR NEW.details IS NOT OLD.details BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER validation_results_no_replace BEFORE INSERT ON validation_results WHEN EXISTS(SELECT 1 FROM validation_results WHERE (validation_result_id=NEW.validation_result_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER validation_results_retain BEFORE DELETE ON validation_results BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX validation_results_fk_0 ON validation_results(conversion_run_id);
