# IDShield AI — SIH 2026, PS 21688

[Download the Windows app](https://github.com/KR1SHNA464/idshield-ai/releases/download/v1.0.0/IDShield-AI-Windows.exe) · [Open the v1.0.0 release](https://github.com/KR1SHNA464/idshield-ai/releases/tag/v1.0.0) · [View the hosted interface](https://idshield-ai-sih2026-21688.vivek420pandia.chatgpt.site)

**NO LIVE GOVERNMENT DATABASE INTEGRATION — ALL VERIFICATION RUNS LOCALLY WITHIN THIS APP.**

IDShield AI is a decision-support prototype. It computes a risk score, independent evidence signals, and plain-language explanations from images supplied by a consenting participant. It never produces an automatic allow/deny result. Approve, Escalate, Reject, and Request Recapture are attributable human officer actions.

“Real input” means a document or face image that a team member or consenting volunteer supplies to the local pipeline. It never means checking Aadhaar, passports, watchlists, government records, or an external identity-verification service.

## Fast judge handoff

The primary handoff is `IDShield-AI-Windows.exe`, a double-click Windows x64 launcher. It includes the React interface, Python/FastAPI engine, OCR runtime, OpenCV models, encrypted SQLite store, and Cloudflare Quick Tunnel helper. No Python, Docker, account, installation, or terminal is required.

The launcher enforces one running instance and displays three access choices:

1. **Stable on this computer:** always opens `http://127.0.0.1:8765` automatically. Reopening the executable focuses this same dashboard instead of starting a duplicate engine.
2. **Same Wi-Fi / LAN:** displays and copies `http://<local-IP>:8765` for nearby phones and laptops. Windows may ask to allow the app through the private-network firewall. Mobile browsers usually require HTTPS for `getUserMedia`, so file/camera-picker upload remains available on LAN while the live webcam button is best used through localhost or the HTTPS tunnel.
3. **Mobile HTTPS:** the launcher automatically creates and copies a temporary `trycloudflare.com` URL through the bundled Cloudflare Quick Tunnel over HTTP/2, with Windows OpenSSH and localhost.run as fallback. A background health check replaces an expired link. These no-account hostnames cannot be bookmarked across launcher sessions. The screening engine still runs on the host machine, while browser traffic passes through the selected tunnel provider; use this only with informed consent and prefer synthetic specimens for remote judging.

Closing the launcher with its **X** button minimizes it and keeps the local server and mobile tunnel running. Use **Stop engine and exit** inside the launcher when you intentionally want to shut both links down. Reopening the executable restores the existing launcher and dashboard. The executable is an unsigned hackathon prototype for Windows x64.

For reliable direct screening on the Windows computer, use the fixed local page that the launcher opens automatically. It serves the UI and Python engine together, so no engine-link connection is required. The public URL is for remote devices and changes whenever the Quick Tunnel is replaced. The separate hosted Sites page can still connect manually when needed, but it has no Python backend by itself.

## Architecture and actual stack

```text
React + TypeScript + Tailwind + shadcn/ui + Recharts
           │ same-origin JSON/multipart API, signed session ID
FastAPI / Python ── literal five-stage pipeline
           │ SQLAlchemy ORM + Fernet-encrypted JSON/blob fields
PostgreSQL (Compose) / SQLite (Windows launcher)
           │ session memory by default; explicit encrypted save
OpenCV quality + forensics → RapidOCR → ICAO MRZ arithmetic
           │
YuNet face detection → trained SFace 128-D embedding → cosine score
```

| Pitch claim | What runs | Honest boundary or substitution |
|---|---|---|
| React, TypeScript, Tailwind, shadcn/ui, Recharts | Responsive officer dashboard, evidence viewer, controls, and risk/activity charts | Sites/Vinext hosts the seeded companion; a Vite SPA is served by FastAPI/nginx for the full engine |
| Python, FastAPI, PostgreSQL, SQLAlchemy | FastAPI and SQLAlchemy; PostgreSQL 16 in Compose | Packaged Windows uses encrypted SQLite, as permitted by the brief |
| OpenCV preprocessing | Resolution, Laplacian blur variance, brightness, under/overexposure, and saturation measurements | Conservative heuristics can reject unusual but usable captures |
| PaddleOCR | RapidOCR 1.4.4 with bundled Paddle-derived ONNX models and ONNX Runtime | Lighter runtime than full PaddleOCR/PaddlePaddle; OCR is actual local pixel inference, never a cloud call |
| MRZ extraction | General OCR plus pixel glyph recognition for fixed-layout generated specimens; TD1/TD2/TD3 parsing and ICAO check digits | Arbitrary layouts depend on OCR legibility; an officer can correct the MRZ transcription and rerun, with the correction audited |
| InsightFace/ArcFace + PyTorch | OpenCV Zoo YuNet detection and trained SFace recognition model with 128-D embeddings and cosine similarity | This is the allowed lightweight face-model substitution. Runtime inference uses OpenCV DNN rather than PyTorch. Scores are not calibrated identity probabilities |
| AI forensics | Four independently reported OpenCV measurements | Font/component variation, JPEG ELA residual ratio, portrait-boundary edge density, and security-region texture. They surface anomalies for review; they do not prove fraud, cloning, hologram validity, or deepfakes |
| Liveness | Webcam-only signed short-lived capture challenge | Confirms the app’s fresh capture path. It is not production anti-spoofing or replay-resistant liveness |
| Cross-document intelligence | Normalized name/DOB consistency, same-type document-number checks, document-face consistency, and SFace search across the current session plus explicitly saved cases | No government, watchlist, or external biometric index |
| Explainable risk | Disclosed additive rule score capped at 100 | Risk bands prioritize human review; they are not fraud probabilities |

The ONNX model hashes and origins are recorded in `THIRD_PARTY_NOTICES.md`.

## Five visible stages

1. **Intake:** accepts two to four PNG/JPEG/PDF documents up to 8 MB each so every live case includes cross-document evidence. It supports upload and `getUserMedia` document capture. OpenCV checks minimum 600×350 resolution, sharpness, extreme exposure, and glare. A failure stops before OCR and requests recapture. Only the first page of a PDF is analyzed; documents above five pages are rejected.
2. **Extraction:** actual local OCR produces structured visible fields where legible. TD1, TD2, and TD3 MRZ parsers validate document number, DOB, expiry, optional data, and composite check digits with ICAO 7/3/1 arithmetic. Available visible and MRZ values are compared; missing values stay unassessed.
3. **Forensics:** font spacing, ELA residual, photo-boundary, and security-region signals each expose the measured value, threshold, confidence, method, and highlighted region. These are lightweight forensic checks, not document-authenticity proof.
4. **Intelligence:** YuNet detects faces and SFace computes trained 128-D embeddings. The engine reports measured cosine similarity against OpenCV’s 0.363 same-identity reference threshold, checks faces and fields across documents and retained consented cases, and records whether the comparison came through the fresh webcam challenge.
5. **Decision:** shows the score calculation and every contributing explanation. A human officer records the outcome and rationale. Version checks prevent decisions on stale evidence; only a supervisor can revise a recorded decision.

## Live privacy behavior

- **Consent first:** the camera and processing actions remain disabled until the officer confirms every subject consented.
- **Session memory by default:** live document bytes, face capture, OCR, thumbnails, and embedding are held only in RAM for that signed session. They expire after four idle hours, disappear on launcher shutdown, and are inaccessible from another login session.
- **Explicit persistence:** **Save this case** copies a reviewed session case to encrypted SQLAlchemy storage. Nothing live is silently persisted.
- **Deletion:** **Delete case** removes the case row, document bytes, thumbnails, and face embedding. The creator can delete their saved case; supervisors and admins can delete saved cases. Any session owner can delete their session case.
- **Audit:** session-only events stay in memory. Saved-case decisions append encrypted, immutable audit records chained with SHA-256 and protected by SQL triggers. Audit snapshots retain fields, measurements, explanations, and the officer outcome while deliberately excluding images and embeddings, so case deletion removes those sensitive assets.
- **At-rest encryption:** Fernet authenticated encryption protects saved case payloads, document bytes, and audit payloads. Keys are generated in the private app data directory unless environment secrets are supplied. This is prototype field-level protection, not a hardware-backed production KMS.
- **RBAC:** every data/action endpoint requires a signed officer, supervisor, or admin token. Officer and supervisor can screen and decide; supervisor can revise decisions and verify the audit chain; admin can manage deletion/purge and verify the chain but cannot decide.

Do not use a real person’s document or face without their knowledge and explicit permission. For a public tunnel demonstration, synthetic fixtures are the safest choice.

## Seeded edge cases

`backend/app/synthetic.py` generates 10 fictional UTO passport-style fixtures marked **SYNTHETIC / SPECIMEN / NOT VALID FOR TRAVEL**. They cover a valid specimen, bad MRZ check digits, visible/MRZ mismatch, photo boundary edit, ELA/font anomaly, blank security region, low controlled portrait similarity, repeated generated portrait under different names, and blur recapture.

Seeded dashboard values are controlled ground truth for a reliable judging walkthrough. **New screening → Seeded scenarios** in the local engine generates fresh pixels and runs the actual OCR/CV pipeline; measured heuristic outputs can differ from the fixture labels. Seeded face scores are labeled fixture values because the illustrated avatars are not human faces.

Regenerate the data with:

```powershell
py -3.12 -c "from backend.app.synthetic import export_demo; export_demo('public/demo','lib/demo-data.json')"
```

## Two-minute judging script

| Time | Demonstration |
|---|---|
| 00:00 | Double-click the launcher. Point out localhost, same-Wi-Fi, and temporary HTTPS links plus the no-government-database disclaimer. |
| 00:15 | Choose **New live screening**. Confirm consent and upload two images: the original/reference document first and the suspected edited copy second. A fresh traveller webcam capture is optional but enables face comparison and the capture-freshness signal. |
| 00:35 | Watch the five-stage stepper. Open Extraction for OCR/MRZ evidence, Forensics for measured pixel signals, and Intelligence for the freshly computed SFace score. |
| 00:55 | Show that the live case says **Session only**. Record one officer action and rationale; explain that the system never chooses it. Use **Save this case** only if the volunteer agreed, or **Delete case** to erase it. |
| 01:15 | Compare Document 1 and Document 2. Expand each document’s OCR/MRZ result, its measured font/ELA/photo/security signals, and the cross-document name, DOB, document-number, and face consistency evidence. The suspected edit is flagged only when a measured threshold or field check actually fails. |
| 01:40 | If an edited image does not cross a heuristic threshold, explain that this prototype correctly leaves it for human review rather than inventing a detection. Optional fictional backup cases remain available for guaranteed checksum and splice demonstrations. |
| 01:50 | Open **Audit trail**. Show who acted, what evidence was available, and that media/embedding copies are excluded from immutable records. |

If a real ID is unsuitable for the judging room, use a consenting team member’s college ID or a generated specimen. The live pipeline accepts non-MRZ IDs; unavailable MRZ evidence is explicitly unassessed rather than invented.

## Run from source

With Docker Desktop installed:

```powershell
.\start-demo.ps1
```

Or run `start-demo.bat`. The script builds frontend, backend, and PostgreSQL, exposes port 8080 to the LAN, prints the LAN link, and starts a Quick Tunnel if `cloudflared` is available. A manual one-line fallback is printed if it is absent. Stop the tunnel with Ctrl+C; run `docker compose down` when finished if the fallback path was used.

Direct Compose remains available:

```sh
docker compose up --build
```

Open `http://localhost:8080`. Compose was not available in the authoring environment, so its files were inspected but not runtime-tested here. The same FastAPI tests run with SQLite; PostgreSQL models, encrypted fields, triggers, and advisory locking remain in the Compose path.

For Python development, install `backend/requirements.txt`, run `py -3.12 backend/models/download_models.py` to fetch the checksum-pinned official OpenCV models, build the SPA with `npm run build:desktop`, copy `desktop-dist/desktop/index.html` to `desktop-dist/index.html`, set `IDSHIELD_DATA_DIR`, and run `py -3.12 desktop/launcher.py`. Docker performs the verified model download during its image build. `desktop/build_windows.ps1` reproduces the packaged launcher and automatically downloads checksum-pinned official OpenCV models and Cloudflare's Windows tunnel binary when they are absent.

## Scoring and tests

Quality failure +25 and stops processing; failed check digits on a detected MRZ +30; visible/MRZ field mismatch +26 (incomplete comparable fields +8); passport-only font/spacing +14; ELA +12; passport-only photo boundary +20; passport-only security texture +12; localized original-versus-copy pixel change +18; measured portrait mismatch +35; cross-document identity conflict +50; and a static comparison portrait without a fresh webcam challenge +4. Cross-document checks normalize and compare names and dates of birth, plus document numbers when two uploads are the same detected type (for example, two PAN cards). Different document numbers across different types, such as one PAN and one Aadhaar belonging to the same person, do not create a conflict on their own. Missing MRZ and missing optional face input add zero risk, which prevents PAN/Aadhaar/college IDs from being penalized for passport-only evidence. Contributions are visible, summed, and capped at 100. Low is 0–24, Medium 25–49, High 50–100.

`backend/tests/test_engine.py` covers ICAO check digits, corrupt lines, actual local OCR, PDF decoding, blur gating, authentication/RBAC, encrypted database values, immutable audit triggers, stale-decision protection, audit-chain verification, consent/type checks, session isolation, opt-in save, media-minimized audit snapshots, real deletion, and a complete five-stage upload.

The packaging smoke test starts the frozen application, signs in, confirms the 10 seeded cases and SFace assets, runs a generated specimen through all five stages, verifies OCR/MRZ output, and checks that the dashboard is served.

## Explicit non-goals

No government API or database, Aadhaar/passport lookup, autonomous admission decision, production liveness, calibrated biometric identity claim, production copy-move/deepfake/hologram/security-thread validation, nonconsensual capture, or offline synchronization is implemented or claimed. Permanent cloud hosting is optional future work; the packaged LAN and temporary tunnel links cover the judging handoff.

Primary references: [ICAO Doc 9303](https://www.icao.int/publications/pages/publication.aspx?docnum=9303), [OpenCV SFace/YuNet tutorial](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html), [OpenCV Zoo](https://github.com/opencv/opencv_zoo), [RapidOCR](https://github.com/RapidAI/RapidOCR), and [Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/).
