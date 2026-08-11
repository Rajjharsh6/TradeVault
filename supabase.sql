-- =========================================================
-- TradeVault - Supabase SQL Schema
-- Run this in the Supabase SQL Editor
-- =========================================================

-- Enable UUID generation (usually already enabled on Supabase)
create extension if not exists "uuid-ossp";

-- =========================================================
-- TABLE: profiles
-- =========================================================
create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    email text,
    default_currency text default 'USD',
    default_platform text default 'MT5',
    default_timezone text default 'UTC',
    default_risk_percent numeric default 1.0,
    theme text default 'dark',
    created_at timestamptz default now()
);

alter table public.profiles enable row level security;

create policy "profiles_select_own"
    on public.profiles for select
    using (auth.uid() = id);

create policy "profiles_insert_own"
    on public.profiles for insert
    with check (auth.uid() = id);

create policy "profiles_update_own"
    on public.profiles for update
    using (auth.uid() = id);

-- Automatically create a profile row when a new user signs up
create or replace function public.handle_new_user()
returns trigger as $$
begin
    insert into public.profiles (id, email)
    values (new.id, new.email)
    on conflict (id) do nothing;
    return new;
end;
$$ language plpgsql security definer;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute procedure public.handle_new_user();

-- =========================================================
-- TABLE: trades
-- =========================================================
create table if not exists public.trades (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references auth.users(id) on delete cascade,
    trade_date date not null,
    symbol text not null,
    direction text not null check (direction in ('Long', 'Short')),
    entry_price numeric not null,
    exit_price numeric,
    stop_loss numeric,
    take_profit numeric,
    lot_size numeric,
    risk_percent numeric,
    profit_loss numeric default 0,
    strategy text,
    session text,
    timeframe text,
    market_condition text,
    result text check (result in ('Win', 'Loss', 'Breakeven')),
    notes text,
    mistakes text,
    emotions text,
    screenshot_url text,
    created_at timestamptz default now()
);

alter table public.trades enable row level security;

create policy "trades_select_own"
    on public.trades for select
    using (auth.uid() = user_id);

create policy "trades_insert_own"
    on public.trades for insert
    with check (auth.uid() = user_id);

create policy "trades_update_own"
    on public.trades for update
    using (auth.uid() = user_id);

create policy "trades_delete_own"
    on public.trades for delete
    using (auth.uid() = user_id);

create index if not exists idx_trades_user_id on public.trades(user_id);
create index if not exists idx_trades_trade_date on public.trades(trade_date);
