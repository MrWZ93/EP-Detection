# Deployment state and remaining gates

## Completed locally

- On-demand TDMS reading with original path context, SHA256 identity, bounded min/max overview and zoom reads.
- Immutable SQLite revisions, independent repeat assessments, atomic outbox transaction, compare-and-swap and operation-ID retries.
- English review workflow, browser recovery drafts, separate local/cloud status.
- Supabase membership/RLS and RPC scripts tested in an isolated local PostgreSQL instance with synthetic data.
- Administrator comparison and explicit EV/BV adjudication code; exact boundary extraction rehashes the local source.
- Apple Silicon application includes Python, native Tcl/Tk picker, NumPy and npTDMS. Executable self-test and loopback HTTP startup are checked separately from GUI acceptance.

## Not completed by publishing this preview

Live Supabase tables, membership grants, auth configuration and publishable key have not been installed. No real study login or synchronization has been demonstrated. The configured project URL is public configuration, not a credential. Empty publishable_key intentionally disables login. No service-role key is accepted or bundled.

Do not deploy the SQL from preview.1 or preview.2. A coordinator with authorization must review/apply the single fresh-install migration documented in [CLOUD_SECURITY_PREVIEW3.md](CLOUD_SECURITY_PREVIEW3.md) to the EP project, create/invite study accounts, explicitly insert members and administrator roles, configure email OTP or Google and the exact loopback redirect http://127.0.0.1:8780/, and supply only a public publishable key in cloud_config.json before rebuilding. Reviewers do not perform these steps. Adding roles is an administrative action, never a client-side name setting.

Schema scripts intentionally fail if their tables already exist: inspect/migrate existing data instead of replacing it. There is no destructive reset command. Back up the project before migrations. The scripts do not touch unrelated application schemas.

The local integration tests emulate Supabase auth.uid and roles; they are not evidence of a live Supabase deployment or complete PostgREST behavior. Run the same cross-user denial, administrator-only, retry/CAS, logout and offline-resume scenarios against the configured study before a connected release.

## Security and scientific limits

The local computer's OS account is the trust boundary for local files. Cloud authority derives from Supabase's verified user and database membership/RLS. A local offline account label grants no cloud access. Preview-local reviews are not silently reassigned to a later signed-in account.

Source identity combines SHA256 and relative path. Root-folder relocation preserves identity; relative-path changes create a separate alias. Duplicates are excluded from pooled strict statistics until resolved. No automatic cross-device merge of conflicting assessments occurs. Conflict exports remain available for adjudication.

Cloud exact-voltage evidence is administrator-attested: the desktop rehashes and reads the exact local source sample, but the cloud does not possess the waveform to independently prove that value. Explicit qualification is required. No claim of physically confirmed rupture follows from S4.

## Distribution

Public source/tutorial/package publication was authorized for this repository. Retain the existing LICENSE. Only synthetic test fixtures generated at runtime are allowed. A release must not include local_evidence, real recovery exports, state databases, source catalogs, TDMS, logs, .venv, or credentials.

The Mac application is ad-hoc signed by the packager, not Developer ID signed or notarized. Request the appropriate developer account/certificate authorization before notarization; do not bypass Gatekeeper. Real Chromium acceptance was run against packaged Mac and Windows executables. Native OS GUI acceptance remains pending; Safari/CUA was unavailable. Windows x64 now has a successful standard windows-2022 build, executable self-test and real Chromium HTTP/review/restart acceptance. Explorer/SmartScreen/native folder-dialog checks remain manual.
