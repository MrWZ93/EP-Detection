# EP Desktop

Local TDMS review with an English browser interface. Python and dependencies are bundled in the Mac application. Raw recordings stay on the reviewer's computer; only annotations, relative source context, hashes, and progress are designed to sync to the EP study.

**1.0.0-preview.2 is a Windows x64 local preview. Live Supabase login/sync is not configured.** The portable Windows executable was built and tested on Windows, including self-test, HTTP, real Chromium Yes/No review, boundary drag/zoom/add and process restart recovery. Reviewers do not install Python. Explorer/SmartScreen/native folder-dialog checks remain manual, and the app is not code-signed. The earlier Mac preview is retained separately.

- [English download and tutorial](https://mrwz93.github.io/EP-Detection/)
- [Releases](https://github.com/MrWZ93/EP-Detection/releases)
- [Release notes](docs/RELEASE_NOTES.md)
- [Deployment and verification boundaries](docs/DEPLOYMENT.md)

## Reviewer workflow

On Windows, extract the entire EP Desktop folder and double-click EP Desktop.exe. Choose a local TDMS folder, sign in when the connected study release is enabled, and enter your name. Browse/search original paths. Open one recording, write a review note, and choose Yes / No / Uncertain. No saves locally before advancing. Yes enables double-click boundaries, drag adjustment, zoom, and region labels. Complete and next saves a new immutable revision. New independent assessment preserves all earlier assessments.

Local saving and cloud acknowledgment are distinct. Export recovery makes an additional annotation backup. Do not upload recovery exports to public issues.

The app uses loopback port 8780 and a separate application-data directory. It does not stop or modify older tools. A random local session secret protects API access. The root picker is native; selected directories are remembered locally.

## Scientific handling

Channel mapping requires unique NI_ArrayColumn 0 and 1. Command voltage is divided by ten only after explicit acquisition-profile confirmation. Current remains raw; alpha/beta and channel 3 are not inferred. Missing sampling intervals produce a sample-index axis, not an assumed 50 kHz. A coordinator places the private ep-dataset-profile.json at the authorized TDMS root. Folder selection automatically loads this content-hash profile and displays the confirmed rate and its evidence source. It is distributed privately alongside the study data. Unknown new files still require verification. A reviewer can enter a verified rate with its basis when needed.

S1–S4 stages may be absent. No return to an earlier stage is accepted. S4 is terminal stable-high morphology, not proof of physical rupture. QC/withdrawal and uncertain post-QC continuity must be documented separately. IV/capacitance filenames do not imply EP.

Administrators require server membership. EV/BV qualification is explicit, exact-boundary based, version matched, and independently audited. BV is never inferred from S4. The cloud holds administrator-attested voltages, not raw samples for independent server verification. Stale revisions, uncertain calibration, censoring, saturation, unconfirmed conditions, and duplicate-content aliases are excluded from strict aggregates. n counts source files, not independent membranes.

## Developer setup

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-macos-arm64.lock
npm ci --ignore-scripts
npm run build
.venv/bin/python -m unittest discover -s tests -v
npm test
.venv/bin/python code/launcher.py
```

macOS build:

```sh
.venv/bin/python -m PyInstaller --noconfirm EPDesktop.spec
'dist/EP Desktop.app/Contents/MacOS/EP Desktop' --self-test
```

Use `--headless --state-dir <isolated-test-directory> --port 8781` for executable HTTP tests. The private launch URL is written to that directory, never to public logs. Do not point test state at real annotation state.

Windows developer build: use Python 3.11 on Windows, install `requirements-windows.lock` with `pip --require-hashes`, build the JavaScript bundle, run tests, then PyInstaller with `EPDesktop.spec`. The standard windows-2022 workflow produces a portable ZIP only after packaged browser/restart acceptance succeeds. [Verified Windows run](https://github.com/MrWZ93/EP-Detection/actions/runs/38676685892). Native OS dialog/security prompts still need acceptance.

The repository's existing license is retained. Bundled dependency notices are included in release assets. No experiment data, real annotations, credentials, or original local reports belong in this repository.
