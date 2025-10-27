-- Running upgrade b7e4d2f9c8a1 -> c6f7d8a9b0c1

CREATE TABLE _alembic_tmp_procedures (
    id VARCHAR NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    metadata JSON NOT NULL,
    PRIMARY KEY (id)
);

INSERT INTO _alembic_tmp_procedures (id, name, description, metadata)
    SELECT id, name, description, metadata FROM procedures;

DROP TABLE procedures;

ALTER TABLE _alembic_tmp_procedures RENAME TO procedures;

CREATE TABLE _alembic_tmp_procedure_steps (
    id VARCHAR NOT NULL,
    procedure_id VARCHAR NOT NULL,
    "key" VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    prompt TEXT,
    metadata JSON NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(procedure_id) REFERENCES procedures (id) ON DELETE CASCADE,
    CONSTRAINT uq_procedure_step_key UNIQUE (procedure_id, "key")
);

INSERT INTO _alembic_tmp_procedure_steps (id, procedure_id, "key", title, prompt, metadata, position)
    SELECT id, procedure_id, "key", title, prompt, metadata, position FROM procedure_steps;

DROP TABLE procedure_steps;

ALTER TABLE _alembic_tmp_procedure_steps RENAME TO procedure_steps;

CREATE TABLE procedure_slots (
    id VARCHAR NOT NULL,
    step_id VARCHAR NOT NULL,
    name VARCHAR(255) NOT NULL,
    label VARCHAR(255),
    type VARCHAR(50) NOT NULL,
    description TEXT,
    required BOOLEAN DEFAULT 1 NOT NULL,
    position INTEGER DEFAULT 0 NOT NULL,
    validate VARCHAR(255),
    mask VARCHAR(255),
    options JSON NOT NULL DEFAULT ('[]'),
    metadata JSON NOT NULL DEFAULT ('{}'),
    PRIMARY KEY (id),
    FOREIGN KEY(step_id) REFERENCES procedure_steps (id) ON DELETE CASCADE,
    CONSTRAINT uq_procedure_slot_name UNIQUE (step_id, name)
);

CREATE INDEX ix_procedure_slots_step_id ON procedure_slots (step_id);

CREATE TABLE procedure_step_checklist_items (
    id VARCHAR NOT NULL,
    step_id VARCHAR NOT NULL,
    "key" VARCHAR(255) NOT NULL,
    label VARCHAR(255) NOT NULL,
    description TEXT,
    required BOOLEAN DEFAULT 1 NOT NULL,
    default_state BOOLEAN,
    position INTEGER DEFAULT 0 NOT NULL,
    metadata JSON NOT NULL DEFAULT ('{}'),
    PRIMARY KEY (id),
    FOREIGN KEY(step_id) REFERENCES procedure_steps (id) ON DELETE CASCADE,
    CONSTRAINT uq_procedure_step_checklist_key UNIQUE (step_id, "key")
);

CREATE INDEX ix_procedure_step_checklist_items_step_id ON procedure_step_checklist_items (step_id);

CREATE TABLE procedure_run_slot_values (
    id VARCHAR NOT NULL,
    run_id VARCHAR NOT NULL,
    slot_id VARCHAR NOT NULL,
    value JSON,
    captured_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
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
    is_completed BOOLEAN DEFAULT 0 NOT NULL,
    completed_at DATETIME,
    PRIMARY KEY (id),
    FOREIGN KEY(run_id) REFERENCES procedure_runs (id) ON DELETE CASCADE,
    FOREIGN KEY(checklist_item_id) REFERENCES procedure_step_checklist_items (id) ON DELETE CASCADE,
    CONSTRAINT uq_procedure_run_checklist_item_state UNIQUE (run_id, checklist_item_id)
);

CREATE INDEX ix_procedure_run_checklist_item_states_run_id ON procedure_run_checklist_item_states (run_id);

CREATE INDEX ix_procedure_run_checklist_item_states_item_id ON procedure_run_checklist_item_states (checklist_item_id);

UPDATE alembic_version SET version_num='c6f7d8a9b0c1' WHERE alembic_version.version_num = 'b7e4d2f9c8a1';
