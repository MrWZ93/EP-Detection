# Maintenance preview.3 verification

42 Python tests passed with zero skips, including 17 real PostgreSQL security/RPC tests. Six DOM tests passed. The single migration additionally passed late-collision rollback, existing-object preservation and repeat-refusal checks. PostgreSQL 16.15 and psycopg 3.3.6; synthetic local identities only. One existing Starlette test-client deprecation warning was emitted. See [machine-readable evidence](verification-preview3.json).

The simplified tutorial was checked in real Chromium at 1280×900, 390×844 and 320×700: download visible above the fold, no horizontal overflow, four ordered steps and working disclosure controls. Desktop/mobile screenshots were visually inspected. The separate 11-section training guide includes seven numbered/arrowed screenshots captured from the packaged preview.2 application using only synthetic TDMS, with external browser requests blocked. Its six UI files match Windows runtime source commit 07fbfb22efa73325953cfc0a58362895d1ad982f. Yes/No, zoom, add/drag boundaries, stage labels, saves and restart recovery were exercised. All images, anchors and enlargement links passed at the three viewport widths; mobile screenshots were visually inspected. Native Windows screenshots are not claimed. No application installer was rebuilt. Live Supabase/Auth and native OS acceptance remain unverified.

# Verification — 1.0.0-preview.2

Locally executed on Apple Silicon macOS:

- 29 Python tests passed, including real isolated PostgreSQL RLS/RPC tests (no skips in the full run).
- 6 JavaScript DOM tests passed: boundaries and ordered labels; No advances only after acknowledgment; interrupted save retains operation identity; S4 regression rejection; zoom then add/drag retains source sample coordinates.
- Packaged executable self-test passed with bundled Python/NumPy/npTDMS.
- Packaged headless loopback HTTP launch passed on a separate test port; UI served; local session guard rejected wrong credentials; cloud correctly reported disabled.
- Representative real source reads: ordinary file and largest local file opened, overviewed and zoomed without source modification. Empty/ambiguous-channel input was rejected explicitly. No raw data was uploaded.
- Confirmed dataset profile is scoped to content hashes; unknown contents do not inherit the rate. The private study profile is not part of the public repository or application bundle.
- Embedded Python code filenames were checked for private absolute user paths; none found. Public source/package scans exclude study data and credentials.

Boundaries of this evidence:

- Real Chromium tests against the packaged executable passed on macOS and Windows: Yes/No, drag then zoom then add, private-profile discovery and restart recovery; no page script errors. Two real representative TDMS were displayed and zoomed on Mac with external requests blocked. Safari/CUA, Finder/Explorer double-click, native folder dialogs and security prompts remain unverified.
- PostgreSQL integration is local with synthetic identities, not a live Supabase deployment test.
- Windows execution is verified by run 38676685892. No Windows code signing, Developer ID signing or Apple notarization is claimed.

Windows runner runs 25 applicable Python tests (four SQL tests require the separate local PostgreSQL fixture), six DOM tests and packaged Chromium acceptance. The local complete Python run passed all 29 with no skips.
