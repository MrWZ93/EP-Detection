# Cloud schema maintenance — 1.0.0-preview.3

This is a source/SQL maintenance release. It does not rebuild or replace the existing Windows preview.2 or Mac preview.1 installers. Their local functionality and disabled cloud configuration remain unchanged. Do not deploy SQL from those earlier release tags. No remote Supabase change, Auth configuration, invitation, membership grant or raw-data transfer was performed by this release.

## Changes

Removed members cannot read their prior cloud assessments/revisions or submit new ones. Administrators retain access to all reviewers' original annotations, comments and revision histories for comparison and adjudication. Role membership is stored in the database, never in user-editable JWT metadata. Clients cannot grant roles.

Privileged implementations now live in the non-exposed `ep_private` schema, with fixed `pg_catalog` search paths and explicit authorization. Public RPC names and payloads remain compatible through invoker wrappers. PUBLIC/anon/authenticated default grants are explicitly revoked, then only required SELECT, schema usage and function execution are granted. Authenticated SQL calls to private implementations still check membership/admin authority. Never expose `ep_private` in Data API settings. Clients cannot create objects in it.

Both revision writes and adjudication acquire the same source transaction lock; revision writes then acquire an assessment lock. A decision waiting behind a new review rechecks the committed review set and rejects a stale snapshot. Later reviews can still make a previously valid decision stale; the application excludes stale decisions until adjudicated again. Decision timestamps follow serialized write order, including transactions that started earlier and clock rollback. Same-operation retries return the original acknowledgment; differing operations with an obsolete base revision conflict atomically.

Required fields reject JSON null, wrong types, string-coerced numbers/booleans and missing hashes. Sampling rate must be a finite positive number; included threshold voltage must be finite. Revision and decision UPDATE/DELETE remain prohibited by triggers; clients have no direct write/TRUNCATE privileges. Database owners retain administrative maintenance authority.

## Exact deployment artifact

`supabase/migrations/20261015035952_ep_cloud_security_preview3.sql`

The official pinned Supabase CLI 2.121.0 generated its filename. The file is one atomic transaction containing both reviewed schema components. Use this complete file for an authorized fresh installation, not the two component scripts separately. It intentionally fails on existing objects; it is **not** an upgrade/reset script for a previously deployed study. The test runner verifies that a late object collision preserves the existing object and rolls back all earlier creations, and that repeat application refuses replacement.

Before deployment, run `cloud/preflight_readonly.sql`; confirm the exact target project, absence of conflicting EP tables/functions/schema, and that `ep_private` is not exposed. Inspect existing policies/default grants and Data API schema settings. Authorization must explicitly cover all-reviewer raw annotation/history access for administrators. Do not drop existing objects to make the migration pass. No users or membership rows are created by the migration.

After authorized deployment, inspect RLS, table/function grants and function search paths, run Supabase security/performance advisors, then test with distinct real authenticated reviewer accounts A/B and an authorized admin. Verify cross-user denials, no role escalation, member removal, retry/conflict, immutable history and administrative comparison. Local PostgreSQL tests emulate Auth roles/UID and are not evidence of live Supabase/PostgREST acceptance. No live advisor result is claimed.

## Reproduce the local tests

Install the application's dependencies plus `psycopg[binary]==3.3.6` in a virtual environment. Install PostgreSQL 16 tools normally, then run from the repository root:

```sh
EP_PG_BIN=/path/to/postgresql/bin python tests/run_postgres.py
npm ci --ignore-scripts
npm test
```

The runner creates its own temporary cluster, uses a Unix socket with no TCP listener, adds synthetic Auth identities, applies hostile default grants before the migration, runs the full Python suite, and stops/removes only that temporary cluster. It never accepts a remote database URL or uses study data. Unix-like hosts are required for this runner; Windows UI tests remain separate.

## Login remains a separate deployment step

Prefer an already configured Google OAuth provider if it fits the reviewers' accounts; otherwise provision custom SMTP and pre-created Auth accounts for the existing email-code flow. Use only a publishable key in the client; never a service-role/secret key. Provider enablement, OAuth setup, email delivery and actual login remain unverified for the study project.

Supabase's default SMTP only sends to organization-team addresses and currently allows two messages/hour. Do not give external reviewers project-management access to bypass this limit. New free-tier projects using default SMTP also cannot customize email templates (change effective June 3, 2026); an OTP template therefore cannot be promised without checking SMTP and project eligibility.

Sources checked October 15, 2026:
- https://supabase.com/docs/guides/database/functions
- https://supabase.com/docs/guides/auth/auth-smtp
- https://supabase.com/changelog/46599-changes-to-email-template-customisation-on-free-tier
- https://supabase.com/changelog/postgres-15-19-17-11-breaking-changes (EP schema does not use the affected ltree/pgcrypto PGP/btree_gist/custom-operator features)
- https://supabase.com/changelog/cbc-tls-ciphers-deprecated (live client TLS negotiation still requires connected acceptance)
