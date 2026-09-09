CREATE DATABASE IF NOT EXISTS filmgraph;
USE filmgraph;

CREATE TABLE IF NOT EXISTS films
(
    id String,
    title String,
    label String,
    provenance String,
    created_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (id, created_at);

CREATE TABLE IF NOT EXISTS revisions
(
    id String,
    film_id String,
    revision_number UInt8,
    label String,
    changed_scene String,
    change_summary String,
    before_text String DEFAULT '',
    after_text String DEFAULT '',
    provenance String,
    created_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (film_id, revision_number, created_at);

CREATE TABLE IF NOT EXISTS pipeline_stages
(
    id UUID,
    sequence UInt8,
    name String,
    description String,
    provenance String
)
ENGINE = MergeTree
ORDER BY (sequence, id);

CREATE TABLE IF NOT EXISTS graph_nodes
(
    id UUID,
    kind LowCardinality(String),
    label String,
    sequence UInt8,
    stage_name String,
    status LowCardinality(String),
    film_id String DEFAULT '',
    revision_id String DEFAULT '',
    scene_number Nullable(String),
    beat_number Nullable(UInt16),
    parent_scene_id Nullable(String),
    heading Nullable(String),
    script_text Nullable(String),
    narration_text Nullable(String),
    start_seconds Nullable(Int32),
    end_seconds Nullable(Int32),
    duration_seconds Nullable(Int32),
    metadata String,
    provenance String,
    created_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (sequence, id);

CREATE TABLE IF NOT EXISTS graph_edges
(
    id UUID,
    source_id UUID,
    target_id UUID,
    relation LowCardinality(String),
    weight Float32,
    confidence Float32,
    metadata String,
    provenance String,
    created_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (created_at, id);

CREATE TABLE IF NOT EXISTS impact_assessments
(
    id UUID,
    film_id String,
    revision_id String,
    node_id UUID,
    severity LowCardinality(String),
    summary String,
    delta String,
    provenance String,
    created_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (revision_id, node_id, created_at, id);

CREATE TABLE IF NOT EXISTS runtime_surgery_proposals
(
    id UUID,
    film_id String,
    revision_id String,
    label String,
    delta_seconds Int32,
    result_seconds UInt32,
    cost_delta String,
    confidence Float32,
    recommended UInt8,
    provenance String,
    created_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (revision_id, created_at, id);

CREATE TABLE IF NOT EXISTS delivery_variants
(
    id UUID,
    film_id String,
    revision_id String,
    platform String,
    territory String,
    audio String,
    subtitle String,
    runtime_seconds UInt32,
    status LowCardinality(String),
    provenance String,
    created_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (revision_id, platform, territory, created_at, id);

CREATE TABLE IF NOT EXISTS delivery_conflicts
(
    id UUID,
    variant_id UUID,
    conflict_type LowCardinality(String),
    detail String,
    resolved UInt8,
    provenance String,
    created_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (variant_id, created_at, id);

CREATE TABLE IF NOT EXISTS workflows
(
    id UUID,
    name String,
    stage_sequence String,
    status LowCardinality(String),
    active_stage Nullable(String),
    approval_status LowCardinality(String),
    delivery_status LowCardinality(String),
    provenance String,
    created_at DateTime64(3, 'UTC'),
    updated_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (created_at, id);

CREATE TABLE IF NOT EXISTS workflow_events
(
    id UUID,
    workflow_id UUID,
    sequence UInt32,
    kind LowCardinality(String),
    actor LowCardinality(String),
    payload String,
    provenance String,
    occurred_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (workflow_id, sequence, occurred_at, id);

CREATE TABLE IF NOT EXISTS agent_runs
(
    id UUID,
    workflow_id UUID,
    stage_name Nullable(String),
    model_name String,
    runtime_mode LowCardinality(String),
    status LowCardinality(String),
    prompt String,
    summary Nullable(String),
    provenance String,
    created_at DateTime64(3, 'UTC'),
    updated_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (created_at, id);

CREATE TABLE IF NOT EXISTS agent_events
(
    id UUID,
    run_id UUID,
    sequence UInt32,
    kind LowCardinality(String),
    message String,
    payload String,
    provenance String,
    occurred_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (run_id, sequence, occurred_at, id);

CREATE TABLE IF NOT EXISTS delivery_records
(
    id UUID,
    workflow_id UUID,
    stage_name String,
    destination String,
    status LowCardinality(String),
    artifact_uri Nullable(String),
    provenance String,
    delivered_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (workflow_id, delivered_at, id);
