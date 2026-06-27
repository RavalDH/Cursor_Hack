# PLAN.md — Cursor Hackathon Sudbury 2026

> **Read this before writing any code.** Every teammate and every AI agent (Cursor, Claude, etc.) must follow this plan. Do not expand scope. Do not invent new features. If you think the plan is wrong, say so to the team in one sentence — do not silently deviate.

---

## 1. Mission (one line)

An AI early-warning assistant for underground mines: it takes any sensor reading and, the moment a zone trends dangerous, speaks the exact Ontario Reg 854 safety procedure with the regulation cited — so the crew acts before it's an emergency, not after.

**Track:** Mining & Industrial Innovation
**Team size:** 3
**Time budget:** ~3 hours of build. This is the hard constraint that drives every decision below.

---

## 2. Hard rules (non-negotiable — agents included)

1. **One tight thing, fully working > many half-things.** A connected, rehearsed demo wins. Disconnected polish loses.
2. **Build narrow before wide.** Get one ugly end-to-end slice working FIRST, then make each layer real.
3. **The HTTP contract (Section 6) is frozen at minute 20.** Backend and frontend integrate over it. Nobody changes it without telling the whole team.
4. **No new code in the final 30 minutes.** That time is for rehearsal and submission only.
5. **Cut line is law** (Section 8). When behind, cut in the listed order. Never cut the working `/ask` slice or the pitch.
6. **Agents: do not over-research.** Do not add libraries, databases, or services not named in this plan. If a task isn't in your phase, don't do it.

---

## 3. Architecture (what we're building)

A small backend + a web UI, talking over HTTP.

```
[ Lovable Web UI ]  --HTTP-->  [ FastAPI backend ]  -->  [ Gemini LLM ]
   (renders answer                  /ask, /alert            (generates the
    + citations,                                             cited answer)
    plays voice)                        |
        ^                               v
        |                        [ 5 Reg 854 docs ]
   [ Valsea voice ]              (keyword retrieval)
```

**Core (must work):** retrieval over 5 docs → Gemini cited answer → UI render → voice out.
**Flourish (only if core is solid):** the `/alert` incident trigger (proactive spoken warning).
**Stretch prizes (only if time to spare, see Section 9):** TiDB vector store, Nemotron model.

---

## 4. Environment & tooling — LOCK THESE, everyone match

| Layer | Tool | Notes |
|---|---|---|
| Code editor | **Cursor** | Claim credits early, first-come-first-served |
| Backend | **Python 3.11+, FastAPI, uvicorn** | One file is fine |
| LLM | **Gemini API** | We already know it. Do NOT learn Nemotron under the clock |
| Retrieval | **Plain keyword match** over 5 docs | No vector DB for core. 5 docs don't need one |
| Frontend / UI | **Lovable** (Pro, code `COMM-CURS-7ACB`) | Owns Best UI/UX prize |
| Voice | **Valsea** (55 min, hard cap) | Ration it. Test on canned strings, not while debugging |
| Scraping | **Apify** (`BUILDWITHAPIFY`, $30) | Only if pulling docs live; otherwise paste docs manually |
| Backend host | **Railway** | See critical note below |
| Repo | github.com/RavalDH/Cursor_Hack | |

### ⚠️ Critical environment gotcha — the #1 thing that breaks team demos

Lovable runs as a **hosted web app on Lovable's domain**. It **cannot** reach `localhost:8000` on your laptop. For the UI to call the backend, the backend needs a **public HTTPS URL**.

**Fix (do this in Phase 1, not at demo time):**
- Deploy the FastAPI backend to **Railway** early → get the public URL (e.g. `https://cursor-hack.up.railway.app`).
- Frontend points at that URL, never at localhost.
- Backend must send **CORS headers** allowing the Lovable origin (already in the stub below).

If Railway deploy is fighting you, fallback: run backend locally + expose with an **ngrok tunnel** → use that public URL. Either way, the frontend talks to a public URL.

### Required secrets (each person sets their own, never commit them)
```
GEMINI_API_KEY=...     # backend
VALSEA_API_KEY=...     # voice
```
Put a `.env.example` in the repo with empty keys. Add real `.env` to `.gitignore`. **Never paste keys into chat, screenshots, or commits.**

---

## 5. Repo structure & merge strategy

**We do NOT git-merge tangled code at the end.** The two halves are decoupled and talk over the contract. This is the entire merge strategy.

```
Cursor_Hack/
├── PLAN.md                # this file
├── backend/
│   ├── main.py            # FastAPI: /ask + /alert
│   ├── retrieval.py       # keyword match over docs
│   ├── docs/              # 5 Reg 854 .txt files
│   ├── requirements.txt
│   └── .env.example
├── frontend/              # Lovable export (or link to Lovable project)
└── README.md              # Devpost description (write last)
```

**Branching:** keep it dumb. `main` only, or one branch per person merged early and often. With 3 people for 3 hours, long-lived branches cause more pain than they prevent. Backend person owns `backend/`, frontend person owns `frontend/` — you rarely touch the same files, so conflicts are minimal.

**Integration happens continuously**, not at the end: the moment the backend is deployed (Phase 1), the frontend points at the real URL and you're integrated. You're never waiting for a big merge.

---

## 6. THE CONTRACT (frozen at minute 20)

This is the seam between backend and frontend. Agree it out loud, paste the stub, then everyone builds against it in parallel.

```
POST /ask
  request:  { "question": "what is the procedure when methane exceeds 1.5%?" }
  response: {
    "answer": "Evacuate the zone and restore ventilation before re-entry...",
    "citations": [ { "source": "O. Reg 854 s.123", "text": "..." } ]
  }

GET /alert      (simulated incident trigger; frontend polls this)
  response: {
    "alert": true,
    "zone": "Zone 3",
    "metric": "methane",
    "value": 1.6,
    "threshold": 1.5,
    "answer": "Methane in Zone 3 exceeds threshold. Evacuate and ventilate...",
    "citations": [ { "source": "O. Reg 854 s.123", "text": "..." } ]
  }
```

### Backend stub — paste into `backend/main.py` at minute 20 so frontend can start immediately

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# CORS — REQUIRED so the hosted Lovable UI can call this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten to the Lovable domain if time
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    question: str

@app.post("/ask")
def ask(req: AskRequest):
    # Phase 0: hardcoded. Phase 1: replace with real retrieval + Gemini.
    return {
        "answer": "STUB: evacuate the zone and restore ventilation before re-entry.",
        "citations": [{"source": "O. Reg 854 s.123", "text": "Stub citation text."}],
    }

@app.get("/alert")
def alert():
    return {
        "alert": True,
        "zone": "Zone 3",
        "metric": "methane",
        "value": 1.6,
        "threshold": 1.5,
        "answer": "STUB: methane in Zone 3 exceeds threshold. Evacuate and ventilate.",
        "citations": [{"source": "O. Reg 854 s.123", "text": "Stub citation text."}],
    }

# run: uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 7. Phase plan (owners + exit criteria)

**Roles:**
- **B = Backend** (retrieval, `/ask`, `/alert`, Railway deploy)
- **F = Frontend** (Lovable UI, renders answer + citations, owns UI/UX prize)
- **V = Voice + Pitch** (Valsea wiring, demo script, runs the 60-second pitch)

| Phase | Time | B does | F does | V does | EXIT CRITERIA |
|---|---|---|---|---|---|
| **0. Align** | 0–20 min | Paste stub, deploy to Railway, share URL | Read contract, scaffold Lovable | Write 1-paragraph demo arc on paper | Contract agreed, stub live at public URL |
| **1. Real /ask** | 20–60 min | Keyword retrieval → Gemini, "cite or say you don't know" | Wire UI to real `/ask` URL, render answer + citations | Valsea reads a canned string aloud | `/ask` returns a real cited answer |
| **2. SLICE** | ~60 min | — assemble — | — assemble — | — assemble — | **ONE question → cited answer → spoken → on screen, connected. If not breathing, STOP adding, fix this.** |
| **3. Make real** | 60–120 min | Tune retrieval, clean citations | Polish UI: citation chips, layout, liveliness | Voice reads REAL answers + **text fallback** | Each layer solid, fallback works |
| **4. Flourish** | 120–150 min | `/alert` returns real incident + procedure | Poll `/alert`, animate gas value, show alert | Proactive spoken warning on trip | Incident demo works — **OR cut it** |
| **5. Ship** | 150–180 min | Freeze. Help test | Freeze. Help test | Rehearse pitch 3×, record backup video, submit Devpost | Submitted early, pitch smooth |

---

## 8. Cut line (memorize — when behind, sacrifice in THIS order)

1. TiDB / Nemotron stretch prizes (already optional)
2. Incident trigger / `/alert` flourish
3. Voice → fall back to on-screen text
4. UI flourishes → keep it plain but clean

**NEVER cut:** the working `/ask` slice, or the rehearsed pitch. Those two ARE the demo.

---

## 9. Stretch prizes (ONLY if core is solid with time to spare)

Do not start these until Phase 3 is done and stable.
- **TiDB (Best Use of TiDB):** swap keyword retrieval for TiDB Serverless vector search. High judge-fit (Brent/Glencore does RAG + knowledge graphs). Keep keyword search as fallback.
- **Nemotron (Best Use of Nemotron):** swap Gemini for Nemotron via NVIDIA Brev. Highest friction — last thing to attempt, cut without guilt.

Already covered by the core build: **Best Use of Valsea** (voice) and **Best UI/UX** (Lovable). Don't do extra work for those — just do them well.

---

## 10. The pitch (locked — V owns this, memorize it)

> "Sensors give you a number. They don't tell your crew what to do. Our system takes any sensor reading — over the same MQTT interface a Becker or Tunik device already uses — and the moment a zone trends dangerous, it speaks the exact Reg 854 procedure with the regulation cited. The crew acts before it's an emergency, not after."

**Demo arc:** show a normal question answered with a citation → trip the simulated gas alarm → assistant proactively speaks the procedure → done. 60 seconds. Don't over-explain. Show what works.

---

## 11. Devpost submission checklist (Phase 5)

- [ ] Project name + team name
- [ ] All 3 members listed
- [ ] Problem + solution (use the pitch)
- [ ] Tools used: Cursor, Lovable, Valsea, Gemini, FastAPI, Railway (+ Apify/TiDB if used)
- [ ] Demo link / video / screenshots that actually load
- [ ] **No API keys exposed anywhere**
- [ ] Submitted BEFORE deadline with buffer (portals jam at the end)
