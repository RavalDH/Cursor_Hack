# PLAN.md — Cursor Hackathon Sudbury 2026 (Team of 3)

> **Read this fully before writing any code.** Every teammate and every AI agent (Cursor, Claude) follows this. Do not add tools, libraries, or features not named here. If you think the plan is wrong, say it to the team in one sentence — never silently deviate.

---

## 0. Mission & constraints

**Build:** An AI early-warning assistant for underground mines. It takes any sensor reading and, the moment a zone trends dangerous, speaks the exact Ontario Reg 854 safety procedure with the regulation cited — so the crew acts before it's an emergency.

**Track:** Mining & Industrial Innovation · **Team:** 3 · **Build budget:** ~3 hours.

**The 3 hours drive everything. One tight working thing beats many half-things.**

---

## 1. The three roles (lock before anything else)

| Role | Person | Owns | Primary tools |
|---|---|---|---|
| **B — Backend** | _____ | retrieval, `/ask`, `/alert`, deploy | Cursor, FastAPI, Gemini, Railway, (Apify) |
| **F — Frontend** | _____ | UI, render answer+citations, **UI/UX prize** | Lovable, the backend URL |
| **V — Voice + Pitch** | _____ | voice out, demo script, the 60-sec pitch | Valsea, slides/notes |

Write your names in. Everyone owns their lane; nobody touches another lane's files. That's how 3 people avoid git conflicts.

---

## 2. Tool ownership matrix — what each tool is for, who, when

| Tool | Owner | What it does for us | When it's used |
|---|---|---|---|
| **GitHub** | All | Shared repo, the merge point | Continuously. Pull before every push |
| **Cursor** | All (mostly B) | Write/debug backend code | Phases 0–4 |
| **FastAPI** | B | The backend: `/ask` + `/alert` | Phases 0–4 |
| **Railway** | B | Hosts backend at a **public URL** | Phase 0–1 (deploy early!) |
| **Gemini** | B | LLM that writes the cited answer | Phase 1 onward |
| **Apify** | B | Scrape Reg 854 docs (optional) | Phase 0 only, time-boxed |
| **Lovable** | F | The web UI / dashboard | Phases 0–4 |
| **Valsea** | V | Text-to-speech voice output | Phase 1 onward, rationed |
| **TiDB** | B (stretch) | Vector store for retrieval | Stretch only, after Phase 3 |
| **Devpost** | V | Final submission | Phase 5 |

---

## 3. Deep tool playbook (how to actually use each one)

### 3.1 GitHub — the merge seam (ALL)
The repo is `github.com/RavalDH/Cursor_Hack`. All 3 are collaborators with their **own** tokens (never share one).

**The only rule that matters with 3 people:**
```bash
git pull origin main --no-rebase   # ALWAYS before you push
git add .
git commit -m "clear message"
git push origin main
```
You rarely conflict because B owns `backend/`, F owns `frontend/`. If a push is rejected → `git pull` first, resolve if asked, push again.

**First, add `.gitignore` so nobody commits a key:**
```bash
echo -e ".env\n__pycache__/\n*.pyc\nnode_modules/" > .gitignore
```

### 3.2 Cursor — your build accelerator (ALL, mostly B)
Cursor writes and debugs code from plain-English prompts. Use it well:
- Open the repo folder in Cursor so it sees the whole project + this PLAN.md.
- Good prompts to actually paste:
  - "Read PLAN.md. Build the FastAPI backend in `backend/main.py` exactly matching the contract in Section 5."
  - "Write a keyword retrieval function over the .txt files in backend/docs/ that returns the top 2 matching sections for a question."
  - "This error: [paste]. Explain it and fix it."
  - "Review this for what could break during a live demo."
- **Rule:** read the code it writes. Don't blind-accept. A bug you don't understand at hour 2 is fatal.

### 3.3 FastAPI + Railway — backend and its PUBLIC URL (B)
**Why Railway is non-negotiable:** Lovable is a hosted web app. It **cannot reach `localhost`**. The backend MUST be at a public HTTPS URL or the frontend can't call it. This is the #1 thing that breaks team demos. Deploy in Phase 0–1, not at demo time.

Backend stub (`backend/main.py`) — paste at minute 20 so F can start:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])  # REQUIRED for Lovable

class AskRequest(BaseModel):
    question: str

@app.post("/ask")
def ask(req: AskRequest):
    return {"answer": "STUB: evacuate and restore ventilation.",
            "citations": [{"source": "O. Reg 854 s.123", "text": "stub"}]}

@app.get("/alert")
def alert():
    return {"alert": True, "zone": "Zone 3", "metric": "methane",
            "value": 1.6, "threshold": 1.5,
            "answer": "STUB: methane high, evacuate and ventilate.",
            "citations": [{"source": "O. Reg 854 s.123", "text": "stub"}]}
```
`requirements.txt`: `fastapi`, `uvicorn[standard]`, `google-generativeai`, `python-dotenv`

**Deploy to Railway:** New Project → Deploy from GitHub repo → pick `Cursor_Hack`, root `backend/`. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`. Add env var `GEMINI_API_KEY`. Railway gives a public URL → paste it in the team chat. **That URL is what F points the UI at.**
Fallback if Railway fights you: run locally + `ngrok http 8000` → use the ngrok URL.

### 3.4 Gemini — the cited-answer engine (B)
Phase 1: replace the stub. Retrieve top sections by keyword, then call Gemini with a strict grounding instruction:
```python
import google.generativeai as genai, os
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-1.5-flash")  # fast = good for live demo

SYSTEM = """You are a mine-safety assistant. Answer ONLY from the provided
regulation sections. Cite the section number for every claim. If the sections
don't cover it, say 'Not found in the provided regulations.' Be concise."""

def answer(question, sections):
    ctx = "\n\n".join(sections)
    resp = model.generate_content(f"{SYSTEM}\n\nSECTIONS:\n{ctx}\n\nQUESTION: {question}")
    return resp.text
```
The strict prompt is what gives you *grounded, cited* answers — that's the responsible-AI story the health/data judge respects. Test it returns a real citation before moving on.

### 3.5 Apify — document scraping (B, OPTIONAL, time-boxed to 30 min)
Only if you want to pull Reg 854 live. **Faster path: just paste 5 sections as `.txt` files into `backend/docs/` manually.** 5 docs don't justify a scraper under a clock. If you do use Apify: Console → a website-content-crawler Actor → point at the Ontario e-Laws Reg 854 page → export text. Code `BUILDWITHAPIFY`, $30 credit. Token from Settings → API & Integrations. **Cut Apify the second it costs more than 30 min.**

### 3.6 Lovable — the UI and the UI/UX prize (F)
Pro plan, code `COMM-CURS-7ACB`. F builds here in parallel from minute 20 against the stub URL.
- Prompt Lovable plainly: "Build a mine-safety dashboard. A search box posts a question to `POST {RAILWAY_URL}/ask` and displays the returned `answer` plus each citation as a chip showing its `source`. Add a status panel that polls `GET {RAILWAY_URL}/alert` every 3s; when `alert` is true, show a red banner with the zone, value, and the answer."
- Swap `{RAILWAY_URL}` for B's real Railway URL the moment it exists.
- **This is where Best UI/UX is won:** citation chips, a clean green/yellow/red zone state, smooth alert animation. Make it feel alive.
- Gotcha: if calls fail, it's almost always CORS (check the stub has the middleware) or you're pointing at localhost instead of the public URL.

### 3.7 Valsea — voice output (V)
Free plan: **55 minutes, one-time hard cap.** Ration it.
- Phase 1: get TTS speaking a **canned string** first — prove the pipe before wiring real answers. Don't debug against live credits.
- Get the API key: Valsea → API Keys. Check their docs for the exact TTS endpoint (send text → get audio); don't guess the call, read their quickstart.
- Phase 3: feed it the real `/ask` answer text.
- **Always wire a text fallback**: if voice fails live, the answer still shows on screen. A mic/credit failure must never kill the demo.

### 3.8 TiDB — vector store (B, STRETCH ONLY)
Do not touch until Phase 3 is solid. Swap keyword retrieval for TiDB Serverless vector search (embeddings + similarity). High judge-fit (Glencore judge does RAG + knowledge graphs). Keep keyword search as the fallback path so this can be cut instantly.

---

## 4. Per-person timeline (minute-by-minute, anchor to real start)

| Time | **B (Backend)** | **F (Frontend)** | **V (Voice + Pitch)** |
|---|---|---|---|
| **0–20** | Paste stub, push, **deploy to Railway**, share URL | Read contract, scaffold Lovable, redeem credits | Write 1-paragraph demo arc; set up Valsea key |
| **20–60** | Add docs, keyword retrieval, wire Gemini to `/ask` | Build UI against stub URL; render answer + citations | Valsea speaks a canned string aloud |
| **~60** | **— ALL THREE assemble the vertical slice —** | | one Q → cited answer → spoken → on screen |
| **60–120** | Tune retrieval, clean citation output | Polish UI: chips, zone colors, layout | Voice reads REAL answers + text fallback |
| **120–150** | `/alert` returns real incident + procedure | Poll `/alert`, animate gas value, red banner | Proactive spoken warning on trip |
| **150–180** | **Freeze.** Help test | **Freeze.** Help test | Rehearse pitch 3×, record backup video, **submit Devpost** |

**Exit gate at minute 60:** if the slice isn't breathing, everyone STOPS adding and fixes it together. Nothing proceeds past a broken slice.

---

## 5. The contract (frozen at minute 20 — the seam between B and F)
```
POST /ask
  in:  { "question": "procedure when methane exceeds 1.5%?" }
  out: { "answer": "...", "citations": [ {"source": "O. Reg 854 s.X", "text": "..."} ] }

GET /alert
  out: { "alert": true, "zone": "Zone 3", "metric": "methane",
         "value": 1.6, "threshold": 1.5,
         "answer": "...", "citations": [ {"source": "O. Reg 854 s.X", "text": "..."} ] }
```
B and F build against this independently. Don't change it without telling everyone.

---

## 6. Cut line (memorize — when behind, sacrifice in THIS order)
1. TiDB / Nemotron stretch prizes
2. `/alert` incident trigger (the flourish)
3. Voice → fall back to on-screen text
4. UI flourishes → keep it plain but clean

**NEVER cut:** the working `/ask` slice or the rehearsed pitch. Those two ARE the demo.

---

## 7. When a tool breaks → fallback (no panic, just switch)

| Breaks | Fallback |
|---|---|
| Railway deploy | `ngrok http 8000` on local backend → use that URL |
| Lovable can't reach backend | Check CORS middleware + confirm you're using the **public** URL, not localhost |
| Gemini quota/errors | Hardcode 3 strong answers for the demo questions; demo still runs |
| Valsea voice fails | On-screen text fallback (already wired) |
| Apify too slow | Paste 5 `.txt` docs by hand |
| Git push rejected | `git pull origin main --no-rebase`, resolve, push |
| TiDB fiddly | Keyword retrieval (your default anyway) |

---

## 8. Prizes this build targets (no extra work)
- **Best Use of Valsea** — voice (core).
- **Best UI/UX** — Lovable polish (core).
- **Best Use of TiDB** — only if stretch reached.
- Plus a Mining-track placement on the strength of the demo + pitch.

---

## 9. The pitch (locked — V owns it, memorize)
> "Sensors give you a number. They don't tell your crew what to do. Our system takes any sensor reading — over the same MQTT interface a Becker or Tunik device already uses — and the moment a zone trends dangerous, it speaks the exact Reg 854 procedure with the regulation cited. The crew acts before it's an emergency, not after."

**Demo arc (60s):** normal question → cited answer → trip the simulated alarm → assistant proactively speaks the procedure → done. Show what works, don't over-explain.

---

## 10. Devpost checklist (Phase 5)
- [ ] Project + team name · all 3 members
- [ ] Problem + solution (use the pitch)
- [ ] Tools: Cursor, Lovable, Valsea, Gemini, FastAPI, Railway (+ Apify/TiDB if used)
- [ ] Demo link / video / screenshots that load
- [ ] **No API keys exposed**
- [ ] Submitted early, with buffer
