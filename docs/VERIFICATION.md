# Verification — 1.0.0-preview.1

Locally executed on Apple Silicon macOS:

- 28 Python tests passed, including real isolated PostgreSQL RLS/RPC tests (no skips in the full run).
- 5 JavaScript DOM tests passed: boundaries and ordered labels; No advances only after acknowledgment; interrupted save retains operation identity; S4 regression rejection; zoom then add/drag retains source sample coordinates.
- Packaged executable self-test passed with bundled Python/NumPy/npTDMS.
- Packaged headless loopback HTTP launch passed on a separate test port; UI served; local session guard rejected wrong credentials; cloud correctly reported disabled.
- Representative real source reads: ordinary file and largest local file opened, overviewed and zoomed without source modification. Empty/ambiguous-channel input was rejected explicitly. No raw data was uploaded.
- Confirmed dataset profile is scoped to content hashes; unknown contents do not inherit the rate. The private study profile is not part of the public repository or application bundle.
- Embedded Python code filenames were checked for private absolute user paths; none found. Public source/package scans exclude study data and credentials.

Boundaries of this evidence:

- DOM tests are not full browser interaction tests. No Safari/CUA tool was exposed during this build session; native folder-dialog and full browser acceptance are still pending.
- PostgreSQL integration is local with synthetic identities, not a live Supabase deployment test.
- No Windows execution, Developer ID signing, or Apple notarization is claimed.
