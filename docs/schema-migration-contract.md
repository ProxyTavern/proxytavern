# Schema Migration Contract (Scaffold)

Status: scaffold for controlled upgrades.

## Current behavior
- Runtime checks SQLite `PRAGMA user_version` against `SCHEMA_VERSION`.
- If database version is newer than supported, startup fails fast with `SchemaVersionError`.

## Controlled upgrade path notes
1. Add migration step(s) in `SQLiteState._init_schema` for `current_version < SCHEMA_VERSION`.
2. Keep migrations idempotent and transactional.
3. Add/adjust tests for:
   - forward migration from previous version(s)
   - future-version guard remains fail-fast
   - data preservation for existing queue/session/token tables
4. Bump `SCHEMA_VERSION` only with matching migration + evidence updates.

## Explicit non-goal (current increment)
- No auto-downgrade or compatibility shim for newer database files.
