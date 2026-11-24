create schema if not exists raw;

create table if not exists raw.events (
    key text primary key,
    payload jsonb not null,
    ingested_at timestamptz not null default now()
);

create table if not exists raw.prices (like raw.events including all);
create table if not exists raw.scores (like raw.events including all);
