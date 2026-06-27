# PLAN.md — Underground Mine Gas Safety (Local / Offline)

> Read fully before coding. Team of 3. ~3 hour build. Everything runs **local, no internet** — because that's the real constraint underground. Agents: do not add cloud services. Do not expand scope.

---

## 0. The real problem (why this matters)

Underground mines have **no internet and no cellular**. Rock blocks radio signals. This is not a limitation we're working around — it's THE defining constraint of the environment.

What mines actually use:
- **Leaky feeder** (legacy): a coax cable run through tunnels acting as an antenna. Low bandwidth, voice-mainly, and it **dies the moment the cable is cut** — e.g. a roof fall.
- **Wireless mesh** (modern): nodes placed through the mine that form a **self-healing network** — if one node dies (roof fall, machinery impact), the network **reroutes automatically**. Critically: **no single central server**. Gas monitoring rides this same mesh, zone by zone.

**The safety gap we attack:** sensors report a gas *number*. They don't tell the crew *what to do* about it, and any system that depends on a cloud or a central server fails exactly when it's needed most — during an incident, when comms are damaged. Our system runs **at the edge, offline, per-zone**, and turns a reading into an immediate cited safety action.

---

## 1. What we build TODAY vs what we PITCH

Be ruthless about this line. We have 3 hours and no hardware.

| | BUILD (3 hrs, one laptop) | PITCH (the real design) |
|---|---|---|
| Network | Local MQTT broker = the mesh | Wireless self-healing mesh between zone nodes |
| Zones | 3–4 simulated zone feeds in software | Real sensor node per zone |
| Transport | MQTT pub/sub on localhost | MQTT over the mine mesh, no internet |
| Brain | Runs on the laptop, offline | Edge box underground, syncs at surface |
| Answers | Local template / small local model | Same, on the edge box |
| Voice | Browser speech, offline | On-device TTS in the cap lamp / tablet |

**We do NOT build real Bluetooth/mesh/hardware.** The judge said "Bluetooth to share data between zones" — we honor that by making the **mesh the design** and simulating zones in software. Acting on feedback = put it in the architecture and the pitch. It does NOT mean shipping a radio mesh in 3 hours with no devices.

---

## 2. Architecture (all local, no cloud)

```
  ZONE SIMULATORS (3-4)                 EDGE BACKEND (one laptop)
  each publishes gas readings    -->    MQTT broker (Mosquitto, local)
  methane / CO / temp / airflow            |
  over MQTT topics:                        v
    mine/zone1/gas                  Subscriber + trend detector
    mine/zone2/gas                  (per-zone: is it climbing toward
    mine/zone3/gas                   the danger threshold?)
                                           |
                                           v
                                  FastAPI  -- /zones  /alert  /ask
                                           |
                                  Local docs (Reg 854 .txt)  +  template/local answer
                                           |
                                           v
                                  LOCAL WEB UI (runs on laptop)
                                  zone map green/yellow/red + spoken alert
```

No external calls anywhere in this diagram. That's the point.

---

## 3. The key idea — TREND, not just threshold

Don't just alarm when gas crosses the line. **Detect the trend**: a zone whose methane is *climbing toward* danger gets flagged early, so the crew leaves before it's an emergency. Simple version: compare the last N readings; if rising and projected to cross threshold soon → yellow (warning) before red (danger). This is the differentiator. Say the word "trend" in the pitch.

---

## 4. Roles (team of 3)

| Role | Owns | Lane |
|---|---|---|
| **B — Backend/Edge** | MQTT broker, zone simulators, trend detector, FastAPI | Python |
| **F — Frontend** | Local web UI: zone map, colors, alert banner | Lovable → exported to run local |
| **V — Voice + Pitch** | Browser speech output, demo script, the pitch | Web Speech API + slides |

Each owns their files. B owns `backend/`, F owns `frontend/`. Minimal git conflict.

---

## 5. Tech stack — all offline-capable

| Layer | Tool | Why / offline note |
|---|---|---|
| Message bus | **Mosquitto** (local MQTT broker) | The honest stand-in for the mine mesh. Runs on localhost, no internet |
| Zone feeds | Python `paho-mqtt` publishers | Simulate 3-4 zones, each emitting changing gas values |
| Backend | **FastAPI + uvicorn** | Subscribes to MQTT, exposes `/zones /alert /ask` |
| Retrieval | Keyword match over local `.txt` | Offline. 5 Reg 854 sections |
| Answers | **Template answers** (default) or **Ollama** local model if B is fast | NO cloud LLM. Template = safe and instant |
| Voice | **Browser Web Speech API** (`speechSynthesis`) | Runs in the browser, offline, free, no cap. Replaces Valsea |
| UI | **Lovable** to build, then **export + `npm run dev`** | Build fast in Lovable, run locally for the offline story |
| Editor | Cursor | Write/debug |

**Why template answers over a local LLM:** a local model (Ollama) is a real offline option but adds setup + speed risk under the clock. Template = match the gas type + level to a fixed Reg 854 procedure sentence. Instant, reliable, never breaks live. Use it unless B has clear spare time.

---

## 6. The contract (frozen at minute 20 — seam between B and F)

```
GET /zones
  out: { "zones": [
    { "id": "zone1", "methane": 0.8, "co": 12, "status": "green", "trend": "stable" },
    { "id": "zone3", "methane": 1.4, "co": 18, "status": "yellow", "trend": "rising" }
  ] }

GET /alert
  out: { "alert": true, "zone": "zone3", "metric": "methane",
         "value": 1.6, "threshold": 1.5, "trend": "rising",
         "answer": "...", "citations": [ {"source":"O. Reg 854 s.X","text":"..."} ] }

POST /ask
  in:  { "question": "procedure when methane exceeds 1.5%?" }
  out: { "answer": "...", "citations": [ {"source":"O. Reg 854 s.X","text":"..."} ] }
```

F polls `/zones` every 2-3s to paint the map, and `/alert` to fire the banner. B builds against MQTT; F builds against the stub.

---

## 7. Phase plan (per person, anchor to real start)

| Time | **B (Backend/Edge)** | **F (Frontend)** | **V (Voice + Pitch)** |
|---|---|---|---|
| 0–20 | Install Mosquitto, write stub FastAPI with hardcoded `/zones`+`/alert`, push | Read contract, build UI against stub, fake zone data | Write demo arc; test browser `speechSynthesis` on a canned line |
| 20–60 | Zone simulators publish to MQTT; backend subscribes, computes status | Paint zone map green/yellow/red from `/zones` | Wire speech to read the alert text |
| ~60 | **— assemble vertical slice: zones update on screen, one alert fires + speaks —** | | |
| 60–110 | Add **trend detection** (rising vs stable); `/alert` returns cited procedure | Polish: rising arrows, red alert banner, layout | Speech reads real procedure + on-screen text fallback |
| 110–150 | `/ask` keyword + template answer | Add a question box → answer + citations | Rehearse full demo flow |
| 150–180 | **Freeze.** Export UI to run local, test offline (wifi OFF) | **Freeze.** Confirm it runs with internet off | Rehearse pitch 3×, record backup video, submit |

**Minute-60 gate:** if zones aren't updating + one alert isn't firing+speaking, everyone stops and fixes. No new features past a broken slice.

**Offline proof:** before you're done, **turn the laptop's wifi off and run the whole demo.** If it works with no internet, you've proven the core claim. Do this — it's your strongest moment in front of mining judges.

---

## 8. Cut line (when behind, sacrifice in order)

1. Local LLM (Ollama) → template answers
2. `/ask` question box → keep just the auto-alert flow
3. Voice → on-screen text (already wired)
4. UI polish → plain but clean

**NEVER cut:** zones updating on screen, one alert firing, the offline demo, the pitch.

---

## 9. When something breaks → fallback

| Breaks | Fallback |
|---|---|
| Mosquitto/MQTT setup slow | Skip the broker; backend generates zone values internally on a timer. Same `/zones` output, pitch still says "MQTT over mesh" |
| Ollama local model | Template answers |
| Web Speech API quirky | On-screen text |
| Lovable export won't run local | Run on localhost for the demo, say "edge-deployable" |
| Git push rejected | `git pull origin main --no-rebase`, resolve, push |

If MQTT eats more than ~30 min, drop to the internal-timer fallback. The mesh is the *story*; MQTT is just the cleanest way to show it. Don't let plumbing sink the demo.

---

## 10. The pitch (V owns it — memorize)

> "Underground, there's no internet and no cellular — rock blocks the signal. When a roof fall cuts the cable, any system that relies on a central server goes dark exactly when you need it. Our system runs at the edge, offline, per zone. Sensors share readings over a local self-healing mesh, and the moment a zone *trends* toward dangerous — not just when it crosses the line — it speaks the exact Reg 854 procedure with the regulation cited. The crew gets out before it's an emergency. Today we're demoing the full software on one machine with simulated zones, internet switched off — the mesh is the transport layer in production."

**Demo arc (60s):** show the zone map all green → Zone 3 methane starts climbing → it flips yellow with a rising arrow (the *trend*) → crosses threshold, goes red, banner fires, voice speaks the cited procedure → **turn wifi off, do it again, still works.** Done.

---

## 11. Why this is a real solution (for judge Q&A)

- **Offline-first / edge:** matches the real no-internet constraint; no central-server single point of failure.
- **Self-healing mesh design:** survives roof falls that kill leaky-feeder cable.
- **Per-zone + trend:** early warning, not just an alarm after the fact.
- **Cited to Reg 854:** grounded, auditable safety guidance, not a guess.
- **MQTT transport:** the same lightweight pub/sub used in real industrial sensor networks.

This is the architecture Becker / Maestro / Glencore actually live with. We built the miniature; we pitch the deployment.
