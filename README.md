# IDShield AI — SIH 2026, PS 21688

**SYNTHETIC DATA — DEMO ONLY. NO LIVE GOVERNMENT INTEGRATION.**

IDShield AI is an identity/document **decision-support prototype**. It returns a risk score, independent signals, evidence, and explanations. It never issues an automated allow/deny result. Approve, Escalate, Reject and Request Recapture are explicit, attributable human officer actions.

## Judge handoff

The primary handoff is **IDShield-AI-Windows.exe**, a standalone Windows x64 launcher. Double-click it: a local Python engine starts, the seeded officer dashboard opens in your browser, and the small launcher window stays open while you review. No Python, Docker, terminal, installation, login or external database setup is needed. Close the launcher to stop the server. The binary is an unsigned hackathon prototype. No Mac/Linux binaries were built.

The hosted companion is a **clearly labeled browser simulation**: twenty seeded cases, stage replay, evidence inspection, human decisions and a session-only history. It does **not** claim to run Python, OCR on uploaded files, RBAC enforcement or encrypted durable storage. Its state resets on reload. The executable is the full-engine judging alternative explicitly permitted by the brief.

The complete source and this README are also available through **Demo guide → Download source + Docker Compose** inside the app.

## Architecture and actual stack

```
React + TypeScript + Tailwind + shadcn/ui + Recharts
           │ same-origin JSON/multipart API, signed demo sessions
FastAPI / Python ── explicit five-stage pipeline
           │ SQLAlchemy ORM + Fernet-encrypted JSON/blob fields
PostgreSQL (Docker Compose) / SQLite (Windows package)
           │ encrypted immutable audit snapshots + SHA-256 chain
OpenCV → RapidOCR / Paddle-derived ONNX → transparent image descriptors/rules
```

| Pitch claim | What actually runs | Limit / substitution |
|---|---|---|
| React, TS, Tailwind, shadcn/ui, Recharts | All included; meaningful stacked case-volume and risk-contribution charts | Sites/Vinext hosts the browser companion; a Vite SPA is served by FastAPI in Windows and nginx in Compose |
| Python, FastAPI, PostgreSQL, SQLAlchemy | FastAPI and SQLAlchemy; PostgreSQL 16 in Compose | Packaged Windows uses SQLite, as permitted in the brief |
| OpenCV preprocessing | Resolution, Laplacian blur variance, brightness/saturation checks | Conservative heuristics; document backgrounds can trigger false positives |
| PaddleOCR | RapidOCR 1.4.4 with bundled Paddle-derived ONNX models and ONNX Runtime | Lighter replacement for the full PaddleOCR/PaddlePaddle runtime. Actual visible-field OCR is local and offline; no cloud OCR |
| MRZ extraction | General OCR transcription + actual pixel glyph matching for the generated fixed-layout specimen | Template-specific glyph recognizer reads image pixels, never metadata or reconstructed check digits. Other layouts may require officer-corrected MRZ text, retained in audit |
| ArcFace/InsightFace | Transparent, untrained pooled grayscale visual descriptor + cosine similarity | **Not ArcFace, not calibrated biometrics, not a trained face model.** PyTorch pooling in Compose; OpenCV/NumPy pooling in the small Windows package. This substitution is intentional and visible |
| AI forensics | Four separately reported OpenCV heuristics | Font/component widths; ELA-style JPEG residual ratio; rectangular photo-boundary edges; texture variance in a specimen security region. No proof of fraud, real copy-move detection, hologram or deepfake verification |
| Liveness | Optional fresh-camera capture with short-lived signed challenge and explicit consent | Simplified proxy only. A challenge is not replay-resistant liveness or proof of camera origin |
| Explainable risk | Sum of disclosed risk contributions, capped at 100 | Priority bands are not fraud probabilities; confidence values are illustrative and uncalibrated |
| Cross-document intelligence | Visible-name/DOB consistency; near-identical retained synthetic descriptor under different names | No government lookup or real biometric index; no protected-attribute inference |

## Five concrete stages

1. **Intake:** accepts 1–4 synthetic PNG/JPEG/PDF documents, each ≤8 MB (total ≤25 MB). First PDF page only, with an explicit UI notice; maximum five-page PDF accepted, so provide the ID page separately. OpenCV evaluates minimum 600×350 resolution, blur variance ≥35, extreme lighting and saturation. A failed capture stops the pipeline before OCR and asks for recapture.
2. **Extraction:** actual local OCR returns structured name, DOB, document number, nationality, issue and expiry where legible. TD1 (3×30), TD2 (2×36), and TD3 (2×44) parsers validate number, DOB, expiry and composite check digits using 7/3/1 weights; TD3 optional-data digit is checked too. Unsupported long-number variants/unrecognized lengths remain unassessed. Visible vs. decoded values are compared without inventing missing fields. Officer correction is explicit and audited.
3. **Forensics:** four independent signals, confidence, exact measurement/threshold, and template-specific evidence regions. ELA is labeled a compression proxy and has false positives; it is not claimed to establish cloning.
4. **Intelligence:** optional comparison portrait, simplified liveness signal, cross-document field consistency, synthetic descriptor links and a transparent score. Full-resolution traveller bytes are released after this call. Unavailable signals are explicitly unassessed.
5. **Decision:** presents the full evidence without an automated disposition. An officer supplies an action and rationale. A version check prevents acting on stale evidence. A supervisor is required to revise a recorded decision. Every outcome retains the exact displayed risk/fields/signals/thumbnails in an encrypted audit snapshot.

## Synthetic scenarios

`backend/app/synthetic.py` generates 20 fictional UTO passport-style images with obvious **SYNTHETIC / SPECIMEN / NOT VALID FOR TRAVEL** markings. Names and numbers are fabricated. Portraits are programmatically illustrated avatars, not real people. The MRZ uses a fictional issuer and specimen optional data; clean specimens deliberately have mathematically valid test check digits, and selected specimens have deliberate checksum failures. Valid arithmetic never makes a specimen a travel document.

The initial cases are explicitly **controlled fixtures**: their structured values and scenario signal scores come from the generator, not a claimed live OCR run. Use **New screening → Demo scenarios → Run sample screening** in the Windows/Compose app to run actual OCR and CV on fresh generated pixels. Actual heuristic measurements can differ from the fixture scores. The hosted companion replays fixture stages and says so.

`python -c "from backend.app.synthetic import export_demo; export_demo('public/demo','lib/demo-data.json')"` regenerates the public, synthetic-only fixtures and frontend seed module.

## Two-minute judging script

| Time | What to show |
|---|---|
| 00:00 | Open **Mira Sen, IDS-2026-0019**. Show consistent fields and valid synthetic MRZ check digits. Explain that low risk is not automatic approval. |
| 00:25 | Open **Ishan Roy, IDS-2026-0014**. Extraction → expand document-number and composite checks; show expected vs. observed digits and the checksum input. |
| 00:45 | Open **Tara Bose, IDS-2026-0013**. Expand font/spacing, ELA and photo-boundary signals; the viewer highlights each region. State the heuristic limitations. |
| 01:05 | Open **Dev Khanna, IDS-2026-0018**. Intelligence shows the controlled 61% fixture score against the illustrative 80% threshold. Identity insights shows the same generated portrait under Aarav Mehta and Zoya Nair. |
| 01:25 | Return to Mira Sen. Decision → choose Approve/Escalate/Reject/Request Recapture and enter a rationale. This is the human officer's choice. |
| 01:45 | Audit trail → open the newest event and inspect the evidence snapshot. In the native app, switch to supervisor under Configuration to verify the audit chain. |

For the live core-engine demonstration, run a consistent sample or upload `public/demo/passport-1.png`, then run `passport-8.png` to demonstrate blur gating. Multiple synthetic documents can be uploaded in one case to test consistency.

## Local developer setup

With Docker Desktop installed, from this source directory run:

```sh
docker compose up --build
```

Open `http://localhost:8080`. Frontend, Python backend and PostgreSQL run behind one local origin. The seeded officer session signs in automatically. The Compose port binds to loopback by default; this HTTP loopback is a local desktop/development connection, not an internet deployment. Any shared cloud deployment **must terminate HTTPS** at its ingress and use separate secrets; do not expose this demo's auto-login accounts to sensitive data. The hosted Sites browser companion uses HTTPS.

Docker was not available in the authoring environment, so the Compose configuration was supplied but not executed there. The Python engine was verified against SQLite (including API and actual OCR tests); PostgreSQL-specific triggers/advisory locks are implemented but need a Compose runtime check before a judging deployment.

Python development: install `backend/requirements.txt`, set `IDSHIELD_DATA_DIR` to a private data directory, build the SPA with `npx vite build --config vite.desktop.config.ts`, copy `desktop-dist/desktop/index.html` to `desktop-dist/index.html`, then run `python desktop/launcher.py`. Install CPU PyTorch separately to use its pooling implementation. The small Windows build intentionally omits it and uses the documented NumPy/OpenCV equivalent.

## Security, roles and privacy

- **RBAC:** signed expiring sessions. All data and mutation endpoints enforce explicit role dependencies. `/api/session` is the intentionally public authentication entry point; static synthetic assets are public. Officer: read/screen/initial decisions; supervisor: these plus revision/chain verification; admin: read/chain verification/expiry purge, no decisions. Credentials are `officer-demo`, `supervisor-demo`, `admin-demo`; the UI pre-fills them for synthetic judging only. Environment overrides are supported in the backend, but the role picker intentionally uses demo defaults.
- **At rest:** Fernet-authenticated encryption protects all case payloads (including fields/descriptors/evidence), document bytes and audit snapshots. IDs, action type, timestamp and case status are non-sensitive indexing metadata. Keys come from `ENCRYPTION_KEY`/`AUTH_SECRET`; local fallback keys are generated into the data directory, never embedded in source or binary. File permissions are restricted where supported. Neighboring demo key files are **not** hardware-backed protection against an attacker controlling the machine; use OS vault/KMS-backed secrets for a real system.
- **Append-only design:** SQL triggers reject audit UPDATE/DELETE, plus full immutable snapshots and a SHA-256 chain. PostgreSQL advisory transaction locks serialize audit appends; the desktop single process uses a reentrant lock. Chain verification detects changes relative to the retained chain; this is not external notarization, and a database administrator with keys is outside this demo threat model.
- **Minimization:** originals are encrypted, downsampled to at most 1800px for analysis, and assigned a 24-hour expiry. Admin **Purge expired originals** deletes expired source bytes and appends an audit event. Purge is manual in this prototype. Traveller originals stay in memory for analysis and are discarded afterward. Only small comparison/document thumbnails and descriptors remain in encrypted case/audit snapshots. Retained audit thumbnails are intentionally low-resolution evidence; no claim of indefinite full-resolution retention is made.
- **Windows data:** stored under the user's local application-data `IDShieldAI` directory by default; no raw documents are written as unencrypted temp files. `launcher.log` contains operational messages, not document OCR or personal fields. No analytics or third-party identity lookup is included.
- **Request boundaries:** same-origin API requests, loopback desktop server, upload byte/pixel/page limits, MIME decoding, no arbitrary remote fetches, no CORS wildcard, and explicit synthetic/consent confirmation. The prototype is not production hardened (no enterprise identity provider, formal penetration test or document authenticity validation).
- **Offline direction:** OCR models and data are bundled, identifiers are generated locally, and the pipeline uses repository-independent SQLAlchemy models. The desktop works without a cloud API. Offline synchronization is deliberately not built.

## Scoring

Quality failure +25 and stops downstream work; MRZ failure +30; unreadable MRZ +12; visible-field mismatch +26 (incomplete fields +8); font/spacing +14; ELA proxy +12; photo boundary +20; security texture +12; portrait mismatch +35 (missing comparison +6); identity conflict +28; liveness unassessed +4. Contributions are per document where relevant and capped at 100. Low 0–24, Medium 25–49, High 50–100. All thresholds and contributions are evidence-visible and uncalibrated.

## Tests and packaging

`backend/tests/test_engine.py` checks ICAO arithmetic, corrupt MRZ rejection, actual OCR and PDF decoding, blur gating, role enforcement, encrypted database contents, append-only triggers, stale-decision protection, audit-chain verification, consent/type checks and a full upload pipeline. Use a fresh isolated `IDSHIELD_DATA_DIR` when running `pytest backend/tests -q`.

The Windows package is built with PyInstaller's one-file/windowed mode and includes the React SPA, FastAPI, OpenCV, RapidOCR models/ONNX runtime, SQLite, and source archive. A packaged `--smoke-test` checks its own startup, seeded authenticated API and served dashboard. No Mac/Linux artifacts are provided.

## References and explicit non-goals

MRZ algorithm: [ICAO Doc 9303, Part 3](https://www.icao.int/publications/documents/9303_p3_cons_en.pdf) and [Part 4](https://www.icao.int/publications/documents/9303_p4_cons_en.pdf). OCR substitution: [RapidOCR project](https://github.com/RapidAI/RapidOCR). Packaging: [PyInstaller documentation](https://pyinstaller.org/en/stable/usage.html).

No government API/database integration, real ID scraping, autonomous entry decision, production liveness, trained biometric identity claim, deepfake verification, hologram/security-thread authentication, offline sync, or nonconsensual biometric capture is implemented or claimed.
