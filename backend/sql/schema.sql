-- NurseSync schema for Amazon RDS (PostgreSQL 16).
-- Carried over from the CareBridge Supabase database: same tables, checks and indexes.
-- Differences: staff no longer references Supabase's auth.users; instead auth_sub holds
-- the Cognito user's `sub`. Row Level Security is gone — the database sits in a private
-- subnet and only the API can reach it. attachments is new (S3 objects on a patient).

create extension if not exists pgcrypto;

create table if not exists staff (
    id          uuid primary key default gen_random_uuid(),
    auth_sub    text unique,                 -- Cognito user pool `sub`; null until linked
    full_name   text not null,
    email       text not null unique,
    role        text not null check (role in ('nurse', 'doctor', 'admin')),
    ward        text,
    active      boolean not null default true,
    created_at  timestamptz not null default now()
);

create table if not exists patients (
    id                  uuid primary key default gen_random_uuid(),
    mrn                 text not null unique,
    full_name           text not null,
    ward                text,
    bed                 text,
    assigned_nurse_id   uuid references staff(id) on delete set null,
    assigned_doctor_id  uuid references staff(id) on delete set null,
    status              text not null default 'admitted' check (status in ('admitted', 'discharged')),
    admitted_at         timestamptz not null default now(),
    discharged_at       timestamptz,
    created_at          timestamptz not null default now(),
    constraint patients_discharged_at_matches_status
        check ((status = 'discharged') = (discharged_at is not null))
);
create index if not exists patients_assigned_doctor_idx on patients (assigned_doctor_id);
create index if not exists patients_assigned_nurse_idx on patients (assigned_nurse_id) where status = 'admitted';

create table if not exists shifts (
    id          uuid primary key default gen_random_uuid(),
    nurse_id    uuid not null references staff(id) on delete cascade,
    started_at  timestamptz not null default now(),
    ended_at    timestamptz,
    status      text not null default 'active' check (status in ('active', 'closed')),
    created_at  timestamptz not null default now()
);
create index if not exists shifts_nurse_active_idx on shifts (nurse_id) where status = 'active';
create unique index if not exists shifts_one_active_per_nurse on shifts (nurse_id) where status = 'active';

create table if not exists patient_notes (
    id              uuid primary key default gen_random_uuid(),
    patient_id      uuid not null references patients(id) on delete cascade,
    author_id       uuid not null references staff(id) on delete restrict,
    shift_id        uuid references shifts(id) on delete set null,
    section         text not null check (section in ('detail', 'major_decision')),
    body            text not null check (length(btrim(body)) > 0),
    source          text not null default 'typed' check (source in ('voice', 'typed')),
    raw_transcript  text,
    stt_confidence  double precision,
    created_at      timestamptz not null default now()
);
create index if not exists patient_notes_patient_idx on patient_notes (patient_id, created_at desc);
create index if not exists patient_notes_shift_idx on patient_notes (shift_id);

create table if not exists handoffs (
    id               uuid primary key default gen_random_uuid(),
    patient_id       uuid not null references patients(id) on delete cascade,
    from_nurse_id    uuid not null references staff(id) on delete restrict,
    to_nurse_id      uuid not null references staff(id) on delete restrict,
    from_shift_id    uuid references shifts(id) on delete set null,
    details          text,
    major_decisions  text,
    status           text not null default 'pending'
                     check (status in ('pending', 'accepted', 'declined', 'issue_reported')),
    response_note    text,
    sent_at          timestamptz not null default now(),
    responded_at     timestamptz,
    created_at       timestamptz not null default now(),
    constraint handoffs_no_self_handoff check (from_nurse_id <> to_nurse_id),
    constraint handoffs_reason_required check (
        status not in ('declined', 'issue_reported')
        or length(btrim(coalesce(response_note, ''))) > 0),
    constraint handoffs_responded_at_consistent check (
        (status = 'pending' and responded_at is null)
        or (status <> 'pending' and responded_at is not null))
);
create index if not exists handoffs_inbox_idx on handoffs (to_nurse_id, status, sent_at desc);
create unique index if not exists handoffs_one_pending_per_patient on handoffs (patient_id) where status = 'pending';
create index if not exists handoffs_patient_idx on handoffs (patient_id, sent_at desc);
create index if not exists handoffs_sent_idx on handoffs (from_nurse_id, sent_at desc);

create table if not exists handoff_events (
    id          uuid primary key default gen_random_uuid(),
    handoff_id  uuid not null references handoffs(id) on delete cascade,
    actor_id    uuid not null references staff(id) on delete restrict,
    event       text not null check (event in ('sent', 'viewed', 'accepted', 'declined', 'issue_reported')),
    note        text,
    created_at  timestamptz not null default now()
);
create index if not exists handoff_events_handoff_idx on handoff_events (handoff_id, created_at);

create table if not exists alerts (
    id               uuid primary key default gen_random_uuid(),
    patient_id       uuid not null references patients(id) on delete cascade,
    raised_by        uuid not null references staff(id) on delete restrict,
    doctor_id        uuid not null references staff(id) on delete restrict,
    message          text,
    status           text not null default 'open' check (status in ('open', 'acknowledged', 'resolved')),
    created_at       timestamptz not null default now(),
    acknowledged_at  timestamptz
);
create index if not exists alerts_doctor_open_idx on alerts (doctor_id, status, created_at desc);
create index if not exists alerts_raised_by_idx on alerts (raised_by, created_at desc);

-- new in NurseSync: files (photos, charts) on a patient, stored in S3
create table if not exists attachments (
    id            uuid primary key default gen_random_uuid(),
    patient_id    uuid not null references patients(id) on delete cascade,
    uploaded_by   uuid not null references staff(id) on delete restrict,
    s3_key        text not null unique,
    file_name     text not null,
    content_type  text not null,
    created_at    timestamptz not null default now()
);
create index if not exists attachments_patient_idx on attachments (patient_id, created_at desc);
