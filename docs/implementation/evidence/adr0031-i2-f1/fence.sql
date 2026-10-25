-- C-F1: additional I2-only staging guard; no product DDL is changed.
-- The existing i2_transfer_stage_fence remains byte-for-byte in the predecessor.
CREATE TRIGGER i2_transfer_report_stage_fence BEFORE INSERT ON resource_relations
WHEN NEW.relation_kind COLLATE BINARY='transfer_event_report'
BEGIN SELECT RAISE(ABORT,'Transfer reports require I3-I5 implementation'); END;
