-- Phase 1: Database
-- Pharmacovigilance MVP — initial schema migration
-- Target: Supabase PostgreSQL

create extension if not exists "pgcrypto";

-- ── Enums ─────────────────────────────────────────────────────────────
create type severity_level as enum ('mild', 'moderate', 'severe');
create type risk_level_enum as enum ('low', 'moderate', 'high');
create type condition_status_enum as enum ('active', 'improving', 'resolved', 'persistent', 'recurred');
create type condition_reason_enum as enum ('doctor_diagnosis', 'user_suspected', 'unknown');
create type medication_status_enum as enum ('active', 'completed', 'completed_early', 'paused', 'discontinued');
create type dose_status_enum as enum ('taken', 'missed', 'skipped');
create type confidence_level_enum as enum ('low', 'moderate', 'high');

-- ── Core tables ───────────────────────────────────────────────────────
create table patients (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  age int,
  sex text,
  weight_kg numeric,
  renal_flag boolean not null default false,
  hepatic_flag boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table conditions (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients(id) on delete cascade,
  name text not null,
  status condition_status_enum not null default 'active',
  reason condition_reason_enum not null default 'unknown',
  diagnosed_date date,
  resolved_date date,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table reference_drugs (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  generic_name text,
  drug_class text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Each row = one prescribing course. Re-prescribing the same drug later
-- creates a new row, keeping history clean without a separate courses table.
create table medications (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients(id) on delete cascade,
  condition_id uuid references conditions(id) on delete set null,
  purpose_text text,
  drug_id uuid not null references reference_drugs(id),
  dose text,
  times_per_day int,
  interval_hours numeric,
  duration_days int,
  status medication_status_enum not null default 'active',
  start_date date not null default current_date,
  end_date date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table medication_schedule (
  id uuid primary key default gen_random_uuid(),
  medication_id uuid not null references medications(id) on delete cascade,
  scheduled_time timestamptz not null,
  created_at timestamptz not null default now()
);

create table medication_doses (
  id uuid primary key default gen_random_uuid(),
  medication_id uuid not null references medications(id) on delete cascade,
  schedule_id uuid references medication_schedule(id) on delete set null,
  scheduled_time timestamptz not null,
  status dose_status_enum,
  actual_time timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table symptoms (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients(id) on delete cascade,
  condition_id uuid references conditions(id) on delete set null,
  medication_id uuid references medications(id) on delete set null,
  description text not null,
  severity severity_level not null default 'mild',
  onset_date date not null default current_date,
  resolved_date date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table interaction_rules (
  id uuid primary key default gen_random_uuid(),
  drug_a_id uuid not null references reference_drugs(id),
  drug_b_id uuid not null references reference_drugs(id),
  severity severity_level not null,
  mechanism text,
  recommendation text,
  source text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table adr_rules (
  id uuid primary key default gen_random_uuid(),
  drug_id uuid not null references reference_drugs(id),
  reaction_description text not null,
  severity severity_level not null,
  frequency_class text,
  source text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table timeline_events (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients(id) on delete cascade,
  event_type text not null,
  ref_id uuid,
  event_title text not null,
  event_description text,
  event_time timestamptz not null default now(),
  payload jsonb,
  created_at timestamptz not null default now()
);

-- No patient_context table by design — context is built dynamically at
-- analysis time by patient_context_builder.py to avoid staleness.

create table analysis_runs (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients(id) on delete cascade,
  analysis_version text not null default 'v1.0',
  deterministic_result jsonb,
  safety_score int,
  risk_level risk_level_enum,
  llm_summary text,
  llm_reasoning text,
  llm_recommendations text,
  confidence_score int,
  confidence_level confidence_level_enum,
  created_at timestamptz not null default now()
);

-- ── Indexes ───────────────────────────────────────────────────────────
create index idx_conditions_patient on conditions(patient_id);
create index idx_medications_patient on medications(patient_id);
create index idx_medications_condition on medications(condition_id);
create index idx_schedule_medication on medication_schedule(medication_id);
create index idx_doses_medication on medication_doses(medication_id);
create index idx_doses_scheduled_time on medication_doses(scheduled_time);
create index idx_symptoms_patient on symptoms(patient_id);
create index idx_interaction_rules_drugs on interaction_rules(drug_a_id, drug_b_id);
create index idx_adr_rules_drug on adr_rules(drug_id);
create index idx_timeline_patient on timeline_events(patient_id, event_time desc);
create index idx_analysis_patient on analysis_runs(patient_id, created_at desc);

-- ── Row Level Security (Supabase) ────────────────────────────────────
alter table patients enable row level security;
create policy "Users manage own patients" on patients
  for all using (auth.uid() = user_id);

-- Child tables inherit access via their patient_id's ownership.
alter table conditions enable row level security;
create policy "Users manage own patient conditions" on conditions
  for all using (patient_id in (select id from patients where user_id = auth.uid()));

alter table medications enable row level security;
create policy "Users manage own patient medications" on medications
  for all using (patient_id in (select id from patients where user_id = auth.uid()));

alter table medication_schedule enable row level security;
create policy "Users manage own schedule" on medication_schedule
  for all using (medication_id in (
    select m.id from medications m
    join patients p on p.id = m.patient_id
    where p.user_id = auth.uid()
  ));

alter table medication_doses enable row level security;
create policy "Users manage own doses" on medication_doses
  for all using (medication_id in (
    select m.id from medications m
    join patients p on p.id = m.patient_id
    where p.user_id = auth.uid()
  ));

alter table symptoms enable row level security;
create policy "Users manage own patient symptoms" on symptoms
  for all using (patient_id in (select id from patients where user_id = auth.uid()));

alter table timeline_events enable row level security;
create policy "Users view own patient timeline" on timeline_events
  for all using (patient_id in (select id from patients where user_id = auth.uid()));

alter table analysis_runs enable row level security;
create policy "Users view own patient analysis" on analysis_runs
  for all using (patient_id in (select id from patients where user_id = auth.uid()));

-- reference_drugs, interaction_rules, adr_rules are shared reference data —
-- readable by all authenticated users, not user-owned.
alter table reference_drugs enable row level security;
create policy "Authenticated users read reference_drugs" on reference_drugs
  for select using (auth.role() = 'authenticated');

alter table interaction_rules enable row level security;
create policy "Authenticated users read interaction_rules" on interaction_rules
  for select using (auth.role() = 'authenticated');

alter table adr_rules enable row level security;
create policy "Authenticated users read adr_rules" on adr_rules
  for select using (auth.role() = 'authenticated');
