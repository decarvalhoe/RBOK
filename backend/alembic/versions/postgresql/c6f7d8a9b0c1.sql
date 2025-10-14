BEGIN;

-- Running upgrade b7e4d2f9c8a1 -> c6f7d8a9b0c1

ALTER TABLE procedure_steps DROP COLUMN slots;

ALTER TABLE procedure_steps DROP COLUMN checklists;

CREATE TABLE procedure_slots (
    id VARCHAR NOT NULL, 
    step_id VARCHAR NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    label VARCHAR(255), 
    type VARCHAR(50) NOT NULL, 
    required BOOLEAN DEFAULT true NOT NULL, 
    position INTEGER DEFAULT 0 NOT NULL, 
    configuration JSON NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(step_id) REFERENCES procedure_steps (id) ON DELETE CASCADE, 
    CONSTRAINT uq_procedure_slot_name UNIQUE (step_id, name)
);

CREATE INDEX ix_procedure_slots_step_id ON procedure_slots (step_id);

CREATE TABLE procedure_step_checklist_items (
    id VARCHAR NOT NULL, 
    step_id VARCHAR NOT NULL, 
    key VARCHAR(255) NOT NULL, 
    label VARCHAR(255) NOT NULL, 
    description TEXT, 
    required BOOLEAN DEFAULT true NOT NULL, 
    position INTEGER DEFAULT 0 NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(step_id) REFERENCES procedure_steps (id) ON DELETE CASCADE, 
    CONSTRAINT uq_procedure_step_checklist_key UNIQUE (step_id, key)
);

CREATE INDEX ix_procedure_step_checklist_items_step_id ON procedure_step_checklist_items (step_id);

CREATE TABLE procedure_run_slot_values (
    id VARCHAR NOT NULL, 
    run_id VARCHAR NOT NULL, 
    slot_id VARCHAR NOT NULL, 
    value JSON, 
    captured_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(run_id) REFERENCES procedure_runs (id) ON DELETE CASCADE, 
    FOREIGN KEY(slot_id) REFERENCES procedure_slots (id) ON DELETE CASCADE, 
    CONSTRAINT uq_procedure_run_slot_value UNIQUE (run_id, slot_id)
);

CREATE INDEX ix_procedure_run_slot_values_run_id ON procedure_run_slot_values (run_id);

CREATE INDEX ix_procedure_run_slot_values_slot_id ON procedure_run_slot_values (slot_id);

CREATE TABLE procedure_run_checklist_item_states (
    id VARCHAR NOT NULL, 
    run_id VARCHAR NOT NULL, 
    checklist_item_id VARCHAR NOT NULL, 
    is_completed BOOLEAN DEFAULT false NOT NULL, 
    completed_at TIMESTAMP WITHOUT TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(run_id) REFERENCES procedure_runs (id) ON DELETE CASCADE, 
    FOREIGN KEY(checklist_item_id) REFERENCES procedure_step_checklist_items (id) ON DELETE CASCADE, 
    CONSTRAINT uq_procedure_run_checklist_item_state UNIQUE (run_id, checklist_item_id)
);

CREATE INDEX ix_procedure_run_checklist_item_states_run_id ON procedure_run_checklist_item_states (run_id);

CREATE INDEX ix_procedure_run_checklist_item_states_item_id ON procedure_run_checklist_item_states (checklist_item_id);

UPDATE alembic_version SET version_num='c6f7d8a9b0c1' WHERE alembic_version.version_num = 'b7e4d2f9c8a1';

COMMIT;

