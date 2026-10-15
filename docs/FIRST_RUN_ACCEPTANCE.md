# First-run acceptance and private dataset distribution

## Private dataset profile (preview.2)

The coordinator places `ep-dataset-profile.json` at the root of the privately distributed TDMS folder. The profile contains a confirmed rate, its evidence basis, and SHA256 content identities; it contains no waveform samples. It must not be published in this repository or public release assets. Reviewers only choose the folder: the app discovers the profile automatically and applies it only to matching file contents. Moving the root folder is supported. Unknown content does not inherit the rate. File metadata that conflicts with the profile requires explicit resolution.

The existing study owner's confirmation is 50,000 Hz for the supplied batch. The actual study profile is retained in the private desktop delivery and is not reproduced here. The coordinator adds it once to the authorized data distribution; reviewers do not edit Python, JSON, or per-file sampling settings. Existing original source folders need not be modified: make the coordinator's distribution copy first.

## Remaining native macOS manual checks

Automated Chromium tests cannot prove Finder/Gatekeeper or native folder-dialog behavior. Perform these checks on the downloaded app using a disposable synthetic/test-data folder and separate test account/state:

1. Extract the archive in Finder and double-click EP Desktop.app. Confirm a launcher window and browser workspace appear. If macOS blocks the unnotarized preview, stop and report the exact prompt; do not disable security protections.
2. Click Choose local folder, select the test-data folder in the macOS dialog, and confirm its TDMS files appear. Cancel the dialog once and confirm the prior selection remains.
3. Confirm a coordinator sidecar shows its sampling rate and evidence source without manual import. A file outside that profile must not receive the confirmed rate.
4. Quit with the launcher's Quit button and reopen the app. Confirm the remembered folder and saved review remain. Confirm the old annotation application is still available separately.

Mouse boundary editing, zoom, Yes/No persistence and process restart recovery are covered by the separate real-browser acceptance script when its recorded run succeeds. Do not substitute DOM test results for native or browser acceptance.

## Reproduce browser acceptance

Install developer dependencies with npm ci and install Playwright Chromium. Generate a disposable fixture with `python tests/prepare_browser.py <test-directory>`. Set EP_BROWSER_FIXTURE to that directory and EP_PACKAGED_EXE to the packaged executable, then run `node tests/browser_acceptance.cjs`. The script launches only a loopback test server and a separate Chromium process, uses synthetic TDMS, and closes both afterwards. Never point it at live annotation state.
