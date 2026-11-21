-- Row level security for every CloudDesk table (16 of 16).
--
-- The FastAPI backend connects with the Supabase service-role key, server side only.
-- The browser holds only the anon key and talks to the API, never to these tables, so:
--   * anon gets no policy at all (default deny);
--   * authenticated users may read their own profile row and nothing else;
--   * service_role has an explicit full-access policy on every table.

alter table audit_logs enable row level security;
alter table customers enable row level security;
alter table incidents enable row level security;
alter table products enable row level security;
alter table profiles enable row level security;
alter table support_articles enable row level security;
alter table subscriptions enable row level security;
alter table tickets enable row level security;
alter table workspaces enable row level security;
alter table customer_memory enable row level security;
alter table ticket_messages enable row level security;
alter table workflow_runs enable row level security;
alter table approval_requests enable row level security;
alter table escalations enable row level security;
alter table workflow_events enable row level security;
alter table resolution_actions enable row level security;

create policy "audit_logs_service_role_all" on audit_logs
    for all to service_role using (true) with check (true);
create policy "customers_service_role_all" on customers
    for all to service_role using (true) with check (true);
create policy "incidents_service_role_all" on incidents
    for all to service_role using (true) with check (true);
create policy "products_service_role_all" on products
    for all to service_role using (true) with check (true);
create policy "profiles_service_role_all" on profiles
    for all to service_role using (true) with check (true);
create policy "support_articles_service_role_all" on support_articles
    for all to service_role using (true) with check (true);
create policy "subscriptions_service_role_all" on subscriptions
    for all to service_role using (true) with check (true);
create policy "tickets_service_role_all" on tickets
    for all to service_role using (true) with check (true);
create policy "workspaces_service_role_all" on workspaces
    for all to service_role using (true) with check (true);
create policy "customer_memory_service_role_all" on customer_memory
    for all to service_role using (true) with check (true);
create policy "ticket_messages_service_role_all" on ticket_messages
    for all to service_role using (true) with check (true);
create policy "workflow_runs_service_role_all" on workflow_runs
    for all to service_role using (true) with check (true);
create policy "approval_requests_service_role_all" on approval_requests
    for all to service_role using (true) with check (true);
create policy "escalations_service_role_all" on escalations
    for all to service_role using (true) with check (true);
create policy "workflow_events_service_role_all" on workflow_events
    for all to service_role using (true) with check (true);
create policy "resolution_actions_service_role_all" on resolution_actions
    for all to service_role using (true) with check (true);

create policy "profiles_read_own" on profiles
    for select to authenticated using (id = auth.uid()::text);
