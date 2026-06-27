# Backend Phases — Role B (FastAPI + Gemini + Railway)

> Owner: **B (Backend)**. Source of truth for backend build order. This is a **living
> file** — if a better idea appears mid-build, edit it here and tell F and V.
> Goal: **working backend first**, then layer intelligence. Fast + top-notch.
>
> Contract is frozen in `PLAN.md` §5 and must not change without telling the team.

---

## How we use models (best tool for each job)

| Work type | Use | Examples |
|---|---|---|
| Writing / debugging code | **Best coding agent** | scaffold FastAPI, retrieval fn, wiring Gemini, fixing errors |
| Design / prompts / architecture | **Best reasoning agent** | grounding prompt, retrieval strategy, alert logic, demo-proofing |

Default routing unless the team says otherwise. Name a specific model to override.

---

## Phase 0 — Skeleton + public seam  *(get something live ASAP)*

**Goal:** A runnable FastAPI app exposing the frozen contract as stubs, deployable to a
public URL so F can start immediately.

**Deliverables**
- `backend/main.py` — FastAPI + CORS (`allow_origins=["*"]`), `POST /ask`, `GET /alert` stubs.
- `backend/requirements.txt` — `fastapi`, `uvicorn[standard]`, `google-generativeai`, `python-dotenv`.
- Run command verified: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- (Deploy step done on Railway by B; locally we prove it runs.)

**Done when**
- `POST /ask` returns `{answer, citations[]}`; `GET /alert` returns the full alert shape.
- App boots with no errors; CORS present.

**Model:** coding agent.

---

## Phase 1 — Retrieval + Gemini grounding  *(the real /ask)*

**Goal:** Replace the `/ask` stub with grounded, cited answers from real reg sections.

**Deliverables**
- `backend/docs/` — ~5 Ontario Reg 854 sections as `.txt` (pasted by hand; Apify optional, time-boxed).
- Keyword retrieval returning the top-2 matching sections for a question.
- Gemini wired with the strict grounding system prompt (cite section for every claim;
  say "Not found in the provided regulations." otherwise).
- `GEMINI_API_KEY` read from env via `python-dotenv`.

**Done when**
- A real safety question returns a concise answer **with a real section citation**.

**Model:** reasoning agent for prompt + retrieval strategy; coding agent to implement.

---

## Phase 2 — Real `/alert` incident logic  *(the flourish)*

**Goal:** `/alert` reports a real (or simulated) sensor trip and the matching procedure.

**Deliverables**
- Threshold check (e.g. methane > 1.5%) producing `{alert, zone, metric, value, threshold, answer, citations}`.
- Reuses retrieval + Gemini so the spoken procedure is grounded and cited.

**Done when**
- Tripping the threshold returns a correct, cited procedure in the contract shape.

**Model:** coding agent; reasoning agent for the trip/threshold design.

---

## Phase 3 — Harden for live demo  *(don't let it break on stage)*

**Goal:** Make the backend demo-proof.

**Deliverables**
- Hardcoded fallback answers for the demo questions if Gemini quota/errors hit.
- Error handling around model + retrieval; sane timeouts.
- Lightweight smoke tests for `/ask` and `/alert`.

**Done when**
- Endpoints never 500 in the demo paths; fallbacks proven.

**Model:** coding agent; reasoning agent to enumerate failure modes.

---

## Stretch — TiDB vector retrieval  *(only after Phase 2 is solid)*

Swap keyword retrieval for TiDB Serverless vector search; keep keyword search as the
instant fallback. Per `PLAN.md` §3.8 — do not start until the core slice breathes.

---

## Cut line (mirror of PLAN.md §6)
1. TiDB stretch  2. `/alert` flourish  3. Voice (V's lane)  4. UI flourishes.
**Never cut:** the working `/ask` slice.
