-- Every table is scoped by client_id (agency, multi-client).
CREATE TABLE IF NOT EXISTS clients (
  id INTEGER PRIMARY KEY, name TEXT, url TEXT UNIQUE, sender_email TEXT,
  whatsapp_number TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS facts (            -- Stage 1: every fact carries its source
  id INTEGER PRIMARY KEY, client_id INTEGER, key TEXT, value TEXT,
  source_url TEXT NOT NULL, extracted_at TEXT DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS documents (        -- Stage 2
  id INTEGER PRIMARY KEY, client_id INTEGER, kind TEXT, path TEXT, approved INTEGER DEFAULT 0);

CREATE TABLE IF NOT EXISTS profiles (         -- Stage 3
  id INTEGER PRIMARY KEY, client_id INTEGER, name TEXT, sector TEXT, geography TEXT,
  revenue_band TEXT, size_band TEXT, filters_json TEXT, titles_json TEXT,
  angle TEXT, priority INTEGER, active INTEGER DEFAULT 0);

CREATE TABLE IF NOT EXISTS companies (        -- Stage 4
  id INTEGER PRIMARY KEY, client_id INTEGER, profile_id INTEGER, name TEXT,
  domain TEXT, country TEXT, fit_score REAL, source_url TEXT,
  UNIQUE(client_id, domain));

CREATE TABLE IF NOT EXISTS people (
  id INTEGER PRIMARY KEY, client_id INTEGER, company_id INTEGER, name TEXT, title TEXT,
  linkedin_url TEXT, source_url TEXT, stage TEXT DEFAULT 'Identified');

CREATE TABLE IF NOT EXISTS contacts (         -- confidence + provenance on every channel
  id INTEGER PRIMARY KEY, person_id INTEGER, channel TEXT CHECK(channel IN ('email','phone','whatsapp','linkedin')),
  value TEXT, source TEXT, confidence REAL, verified_at TEXT,
  consent TEXT DEFAULT 'none');               -- none | implied | opted_in

CREATE TABLE IF NOT EXISTS messages (         -- Stage 5 chat log
  id INTEGER PRIMARY KEY, client_id INTEGER, person_id INTEGER, channel TEXT,
  direction TEXT CHECK(direction IN ('out','in')), body TEXT, hook_source TEXT,
  status TEXT DEFAULT 'draft',                -- draft | approved | sent | received | rejected
  classification TEXT, ts TEXT DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, client_id INTEGER, person_id INTEGER, type TEXT, points REAL,
  ts TEXT DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS suppression (
  client_id INTEGER, value TEXT, reason TEXT, ts TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(client_id, value));
