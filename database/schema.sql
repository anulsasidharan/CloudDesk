-- CloudDesk support schema (PostgreSQL / Supabase).
--
-- AUTHORITY for the table list (CLAUDE.md section 20): this file defines 16 tables and
-- RLS is enabled on all 16 (rls_policies.sql). The SQLAlchemy models in
-- backend/app/models/entities.py are the portable form; tests/unit/test_schema_parity.py
-- fails when the two disagree on tables, columns, types or nullability.
--
-- Ids are varchar(36) holding UUID text so the same models run on SQLite and Postgres.
-- Never edit an applied migration: add database/migrations/000N_<name>.sql and update this file.

create or replace function set_updated_at() returns trigger
language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

CREATE TABLE audit_logs (
    id VARCHAR(36) NOT NULL DEFAULT gen_random_uuid()::text,
    actor_id VARCHAR(36),
    actor_email VARCHAR(255),
    method VARCHAR(10) NOT NULL,
    path VARCHAR(500) NOT NULL,
    status_code INTEGER NOT NULL,
    request_id VARCHAR(128),
    detail JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_audit_logs PRIMARY KEY (id)
);

CREATE INDEX ix_audit_logs_request_id ON audit_logs (request_id);

CREATE TABLE customers (
    id VARCHAR(36) NOT NULL DEFAULT gen_random_uuid()::text,
    email VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    company VARCHAR(255) NOT NULL,
    plan VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    timezone VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_customers PRIMARY KEY (id),
    CONSTRAINT ck_customers_plan CHECK (plan IN ('free', 'pro', 'business', 'enterprise')),
    CONSTRAINT uq_customers_email UNIQUE (email)
);

CREATE TABLE incidents (
    id VARCHAR(36) NOT NULL DEFAULT gen_random_uuid()::text,
    title VARCHAR(255) NOT NULL,
    service VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    description TEXT NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_incidents PRIMARY KEY (id),
    CONSTRAINT ck_incidents_status CHECK (status IN ('active', 'resolved')),
    CONSTRAINT ck_incidents_severity CHECK (severity IN ('low', 'medium', 'high', 'critical'))
);

CREATE INDEX ix_incidents_service ON incidents (service);

CREATE TABLE products (
    id VARCHAR(36) NOT NULL DEFAULT gen_random_uuid()::text,
    sku VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    kind VARCHAR(20) NOT NULL,
    monthly_price FLOAT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_products PRIMARY KEY (id),
    CONSTRAINT uq_products_sku UNIQUE (sku)
);

CREATE TABLE profiles (
    id VARCHAR(36) NOT NULL DEFAULT gen_random_uuid()::text,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL,
    avatar_url VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_profiles PRIMARY KEY (id),
    CONSTRAINT ck_profiles_role CHECK (role IN ('viewer', 'agent', 'admin')),
    CONSTRAINT uq_profiles_email UNIQUE (email)
);

CREATE TABLE support_articles (
    id VARCHAR(36) NOT NULL DEFAULT gen_random_uuid()::text,
    slug VARCHAR(120) NOT NULL,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(40) NOT NULL,
    tags JSONB NOT NULL,
    summary TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_support_articles PRIMARY KEY (id),
    CONSTRAINT ck_support_articles_category CHECK (category IN ('login_issue', 'billing', 'api_failure', 'workspace_permissions', 'storage_quota', 'integration', 'feature_request', 'account', 'security', 'other')),
    CONSTRAINT uq_support_articles_slug UNIQUE (slug)
);

CREATE TABLE subscriptions (
    id VARCHAR(36) NOT NULL DEFAULT gen_random_uuid()::text,
    customer_id VARCHAR(36) NOT NULL,
    plan VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    billing_cycle VARCHAR(20) NOT NULL,
    seats_purchased INTEGER NOT NULL,
    seats_used INTEGER NOT NULL,
    seat_price FLOAT NOT NULL,
    currency VARCHAR(3) NOT NULL,
    storage_limit_gb INTEGER NOT NULL,
    storage_used_gb FLOAT NOT NULL,
    api_rate_limit_per_minute INTEGER NOT NULL,
    renews_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_subscriptions PRIMARY KEY (id),
    CONSTRAINT ck_subscriptions_plan CHECK (plan IN ('free', 'pro', 'business', 'enterprise')),
    CONSTRAINT fk_subscriptions_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE
);

CREATE INDEX ix_subscriptions_customer_id ON subscriptions (customer_id);

CREATE TABLE tickets (
    id VARCHAR(36) NOT NULL DEFAULT gen_random_uuid()::text,
    number VARCHAR(20) NOT NULL,
    customer_id VARCHAR(36) NOT NULL,
    assigned_to VARCHAR(36),
    subject VARCHAR(500) NOT NULL,
    body TEXT NOT NULL,
    channel VARCHAR(20) NOT NULL,
    status VARCHAR(30) NOT NULL,
    category VARCHAR(40),
    severity VARCHAR(20),
    severity_reason TEXT,
    summary TEXT,
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_tickets PRIMARY KEY (id),
    CONSTRAINT ck_tickets_status CHECK (status IN ('new', 'in_progress', 'waiting_on_customer', 'waiting_on_approval', 'escalated', 'resolved', 'closed')),
    CONSTRAINT ck_tickets_channel CHECK (channel IN ('email', 'chat', 'web', 'api')),
    CONSTRAINT ck_tickets_category CHECK (category IS NULL OR category IN ('login_issue', 'billing', 'api_failure', 'workspace_permissions', 'storage_quota', 'integration', 'feature_request', 'account', 'security', 'other')),
    CONSTRAINT ck_tickets_severity CHECK (severity IS NULL OR severity IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT uq_tickets_number UNIQUE (number),
    CONSTRAINT fk_tickets_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id),
    CONSTRAINT fk_tickets_assigned_to_profiles FOREIGN KEY(assigned_to) REFERENCES profiles (id)
);

CREATE INDEX ix_tickets_assigned_to ON tickets (assigned_to);

CREATE INDEX ix_tickets_status_created_at ON tickets (status, created_at);

CREATE INDEX ix_tickets_customer_id ON tickets (customer_id);

CREATE TABLE workspaces (
    id VARCHAR(36) NOT NULL DEFAULT gen_random_uuid()::text,
    customer_id VARCHAR(36) NOT NULL,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL,
    region VARCHAR(20) NOT NULL,
    member_count INTEGER NOT NULL,
    storage_used_gb FLOAT NOT NULL,
    sso_enabled BOOLEAN NOT NULL,
    mfa_required BOOLEAN NOT NULL,
    external_sharing BOOLEAN NOT NULL,
    settings JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_workspaces PRIMARY KEY (id),
    CONSTRAINT fk_workspaces_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE,
    CONSTRAINT uq_workspaces_slug UNIQUE (slug)
);

CREATE INDEX ix_workspaces_customer_id ON workspaces (customer_id);

CREATE TABLE customer_memory (
    id VARCHAR(36) NOT NULL DEFAULT gen_random_uuid()::text,
    customer_id VARCHAR(36) NOT NULL,
    kind VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    source_ticket_id VARCHAR(36),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_customer_memory PRIMARY KEY (id),
    CONSTRAINT ck_customer_memory_kind CHECK (kind IN ('preference', 'past_issue', 'troubleshooting', 'note')),
    CONSTRAINT uq_customer_memory_note UNIQUE (customer_id, kind, content_hash),
    CONSTRAINT fk_customer_memory_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE,
    CONSTRAINT fk_customer_memory_source_ticket_id_tickets FOREIGN KEY(source_ticket_id) REFERENCES tickets (id)
);

CREATE INDEX ix_customer_memory_customer_id ON customer_memory (customer_id);

CREATE INDEX ix_customer_memory_source_ticket_id ON customer_memory (source_ticket_id);

CREATE TABLE ticket_messages (
    id VARCHAR(36) NOT NULL DEFAULT gen_random_uuid()::text,
    ticket_id VARCHAR(36) NOT NULL,
    sender_type VARCHAR(20) NOT NULL,
    sender_name VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    is_internal BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_ticket_messages PRIMARY KEY (id),
    CONSTRAINT ck_ticket_messages_sender_type CHECK (sender_type IN ('customer', 'agent', 'system')),
    CONSTRAINT fk_ticket_messages_ticket_id_tickets FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE CASCADE
);

CREATE INDEX ix_ticket_messages_ticket_id ON ticket_messages (ticket_id);

CREATE TABLE workflow_runs (
    id VARCHAR(36) NOT NULL DEFAULT gen_random_uuid()::text,
    ticket_id VARCHAR(36) NOT NULL,
    thread_id VARCHAR(64) NOT NULL,
    status VARCHAR(30) NOT NULL,
    current_node VARCHAR(64),
    state JSONB NOT NULL,
    error TEXT,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_workflow_runs PRIMARY KEY (id),
    CONSTRAINT ck_workflow_runs_status CHECK (status IN ('pending', 'running', 'waiting_on_approval', 'completed', 'failed')),
    CONSTRAINT fk_workflow_runs_ticket_id_tickets FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE CASCADE,
    CONSTRAINT uq_workflow_runs_thread_id UNIQUE (thread_id)
);

CREATE INDEX ix_workflow_runs_ticket_id ON workflow_runs (ticket_id);

CREATE TABLE approval_requests (
    id VARCHAR(36) NOT NULL DEFAULT gen_random_uuid()::text,
    workflow_id VARCHAR(36) NOT NULL,
    ticket_id VARCHAR(36) NOT NULL,
    summary TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    payload JSONB NOT NULL,
    decided_by VARCHAR(36),
    decision_note TEXT,
    decided_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_approval_requests PRIMARY KEY (id),
    CONSTRAINT ck_approval_requests_status CHECK (status IN ('pending', 'approved', 'rejected')),
    CONSTRAINT fk_approval_requests_workflow_id_workflow_runs FOREIGN KEY(workflow_id) REFERENCES workflow_runs (id) ON DELETE CASCADE,
    CONSTRAINT fk_approval_requests_ticket_id_tickets FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE CASCADE,
    CONSTRAINT fk_approval_requests_decided_by_profiles FOREIGN KEY(decided_by) REFERENCES profiles (id)
);

CREATE INDEX ix_approval_requests_decided_by ON approval_requests (decided_by);

CREATE INDEX ix_approval_requests_ticket_id ON approval_requests (ticket_id);

CREATE INDEX ix_approval_requests_workflow_id ON approval_requests (workflow_id);

CREATE TABLE escalations (
    id VARCHAR(36) NOT NULL DEFAULT gen_random_uuid()::text,
    ticket_id VARCHAR(36) NOT NULL,
    workflow_id VARCHAR(36),
    team VARCHAR(64) NOT NULL,
    reason TEXT NOT NULL,
    severity VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_escalations PRIMARY KEY (id),
    CONSTRAINT ck_escalations_status CHECK (status IN ('open', 'acknowledged', 'closed')),
    CONSTRAINT ck_escalations_severity CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT fk_escalations_ticket_id_tickets FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE CASCADE,
    CONSTRAINT fk_escalations_workflow_id_workflow_runs FOREIGN KEY(workflow_id) REFERENCES workflow_runs (id)
);

CREATE INDEX ix_escalations_ticket_id ON escalations (ticket_id);

CREATE INDEX ix_escalations_workflow_id ON escalations (workflow_id);

CREATE TABLE workflow_events (
    id VARCHAR(36) NOT NULL DEFAULT gen_random_uuid()::text,
    workflow_id VARCHAR(36) NOT NULL,
    ticket_id VARCHAR(36) NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    node VARCHAR(64),
    payload JSONB NOT NULL,
    duration_ms INTEGER,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd FLOAT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_workflow_events PRIMARY KEY (id),
    CONSTRAINT ck_workflow_events_event_type CHECK (event_type IN ('node_started', 'node_completed', 'tool_called', 'llm_called', 'approval_requested', 'approval_resolved', 'error', 'workflow_completed')),
    CONSTRAINT fk_workflow_events_workflow_id_workflow_runs FOREIGN KEY(workflow_id) REFERENCES workflow_runs (id) ON DELETE CASCADE,
    CONSTRAINT fk_workflow_events_ticket_id_tickets FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE CASCADE
);

CREATE INDEX ix_workflow_events_workflow_id ON workflow_events (workflow_id);

CREATE INDEX ix_workflow_events_ticket_id ON workflow_events (ticket_id);

CREATE TABLE resolution_actions (
    id VARCHAR(36) NOT NULL DEFAULT gen_random_uuid()::text,
    workflow_id VARCHAR(36) NOT NULL,
    ticket_id VARCHAR(36) NOT NULL,
    approval_id VARCHAR(36),
    tool VARCHAR(64) NOT NULL,
    args JSONB NOT NULL,
    requires_approval BOOLEAN NOT NULL,
    status VARCHAR(30) NOT NULL,
    result JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_resolution_actions PRIMARY KEY (id),
    CONSTRAINT ck_resolution_actions_status CHECK (status IN ('planned', 'awaiting_approval', 'executed', 'failed', 'skipped')),
    CONSTRAINT fk_resolution_actions_workflow_id_workflow_runs FOREIGN KEY(workflow_id) REFERENCES workflow_runs (id) ON DELETE CASCADE,
    CONSTRAINT fk_resolution_actions_ticket_id_tickets FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE CASCADE,
    CONSTRAINT fk_resolution_actions_approval_id_approval_requests FOREIGN KEY(approval_id) REFERENCES approval_requests (id)
);

CREATE INDEX ix_resolution_actions_workflow_id ON resolution_actions (workflow_id);

CREATE INDEX ix_resolution_actions_ticket_id ON resolution_actions (ticket_id);

CREATE INDEX ix_resolution_actions_approval_id ON resolution_actions (approval_id);

-- updated_at triggers (one per table)
create trigger trg_audit_logs_updated_at before update on audit_logs
    for each row execute function set_updated_at();
create trigger trg_customers_updated_at before update on customers
    for each row execute function set_updated_at();
create trigger trg_incidents_updated_at before update on incidents
    for each row execute function set_updated_at();
create trigger trg_products_updated_at before update on products
    for each row execute function set_updated_at();
create trigger trg_profiles_updated_at before update on profiles
    for each row execute function set_updated_at();
create trigger trg_support_articles_updated_at before update on support_articles
    for each row execute function set_updated_at();
create trigger trg_subscriptions_updated_at before update on subscriptions
    for each row execute function set_updated_at();
create trigger trg_tickets_updated_at before update on tickets
    for each row execute function set_updated_at();
create trigger trg_workspaces_updated_at before update on workspaces
    for each row execute function set_updated_at();
create trigger trg_customer_memory_updated_at before update on customer_memory
    for each row execute function set_updated_at();
create trigger trg_ticket_messages_updated_at before update on ticket_messages
    for each row execute function set_updated_at();
create trigger trg_workflow_runs_updated_at before update on workflow_runs
    for each row execute function set_updated_at();
create trigger trg_approval_requests_updated_at before update on approval_requests
    for each row execute function set_updated_at();
create trigger trg_escalations_updated_at before update on escalations
    for each row execute function set_updated_at();
create trigger trg_workflow_events_updated_at before update on workflow_events
    for each row execute function set_updated_at();
create trigger trg_resolution_actions_updated_at before update on resolution_actions
    for each row execute function set_updated_at();
