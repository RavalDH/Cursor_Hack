"""Generate hackathon pitch deck for MineGuard Edge."""

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

# --- Brand palette (mining / safety) ---
BG = RGBColor(15, 23, 42)       # slate-900
ACCENT = RGBColor(245, 158, 11)  # amber-500
GREEN = RGBColor(34, 197, 94)    # green-500
RED = RGBColor(239, 68, 68)      # red-500
WHITE = RGBColor(248, 250, 252)
MUTED = RGBColor(148, 163, 184)
CARD = RGBColor(30, 41, 59)

OUTPUT = Path(__file__).parent / "MineGuard_Edge_Hackathon.pptx"


def set_slide_bg(slide, color=BG):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_textbox(slide, left, top, width, height, text, size=18, bold=False, color=WHITE, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(size)
    p.font.bold = bold
    p.font.color.rgb = color
    p.alignment = align
    return box


def add_bullets(slide, left, top, width, height, items, size=16, color=WHITE, bullet_color=ACCENT):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = item
        p.level = 0
        p.font.size = Pt(size)
        p.font.color.rgb = color
        p.space_after = Pt(8)
    return box


def add_accent_bar(slide, top=0.55):
    shape = slide.shapes.add_shape(
        1, Inches(0.6), Inches(top), Inches(0.08), Inches(0.55)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = ACCENT
    shape.line.fill.background()


def slide_header(slide, title, subtitle=None):
    add_accent_bar(slide)
    add_textbox(slide, 0.85, 0.45, 11.5, 0.7, title, size=32, bold=True)
    if subtitle:
        add_textbox(slide, 0.85, 1.05, 11.5, 0.5, subtitle, size=14, color=MUTED)


def build():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    # 1 — TITLE (Hook category)
    s = prs.slides.add_slide(blank)
    set_slide_bg(s)
    add_textbox(s, 0.9, 2.0, 11.5, 1.2, "MineGuard Edge", size=48, bold=True, align=PP_ALIGN.CENTER)
    add_textbox(
        s, 0.9, 3.2, 11.5, 0.8,
        "Offline AI Safety Intelligence for Underground Mines",
        size=22, color=ACCENT, align=PP_ALIGN.CENTER,
    )
    add_textbox(
        s, 0.9, 4.2, 11.5, 0.6,
        "Cursor Hackathon  ·  Team of 3  ·  100% Local / No Cloud",
        size=14, color=MUTED, align=PP_ALIGN.CENTER,
    )

    # 2 — PROBLEM (most critical slide category)
    s = prs.slides.add_slide(blank)
    set_slide_bg(s)
    slide_header(s, "The Problem", "Why underground safety fails when it matters most")
    add_bullets(s, 0.9, 1.7, 11.2, 4.5, [
        "Underground mines have NO internet and NO cellular — rock blocks every signal",
        "Legacy leaky-feeder cables die the moment a roof fall cuts the line",
        "Sensors report a gas number — they don't tell crews what to do next",
        "Cloud-dependent systems go dark exactly during an incident",
        "Alarms fire AFTER danger — not while methane is still climbing",
    ], size=20)
    add_textbox(s, 0.9, 6.2, 11, 0.5, "Who suffers: miners, shift supervisors, emergency response teams", size=13, color=MUTED)

    # 3 — WHY NOW / CONTEXT
    s = prs.slides.add_slide(blank)
    set_slide_bg(s)
    slide_header(s, "Why Now?", "The industry is moving — but the safety gap remains")
    add_bullets(s, 0.9, 1.7, 5.5, 4.5, [
        "Modern mines deploy wireless mesh (Becker, Maestro, Glencore)",
        "MQTT pub/sub is standard for industrial sensors",
        "Reg 854 mandates specific gas-response procedures",
        "Edge computing makes offline intelligence possible today",
    ], size=17)
    add_textbox(s, 7.0, 1.9, 5.5, 4.5,
        "The gap:\n\n"
        "Mesh moves data.\n"
        "Sensors measure gas.\n\n"
        "Nothing turns a rising reading into an immediate, cited, spoken safety action — offline, at the edge, per zone.",
        size=18, color=ACCENT)

    # 4 — SOLUTION (one-liner + value prop)
    s = prs.slides.add_slide(blank)
    set_slide_bg(s)
    slide_header(s, "Our Solution", "One sentence")
    add_textbox(
        s, 0.9, 1.8, 11.5, 1.2,
        "MineGuard Edge runs offline at every zone, detects dangerous gas trends early, "
        "ramps ventilation automatically, and speaks the exact Reg 854 procedure — with citations.",
        size=22, color=WHITE,
    )
    add_bullets(s, 0.9, 3.3, 11.2, 3.0, [
        "Trend detection — warn BEFORE the threshold, not after",
        "Automated ventilation control — fans ramp to dilute gas (never enrich O₂)",
        "Reg 854-grounded answers — auditable, not a guess",
        "Voice + visual alerts — crew hears the procedure underground",
    ], size=18, bullet_color=GREEN)

    # 5 — HOW IT WORKS / ARCHITECTURE
    s = prs.slides.add_slide(blank)
    set_slide_bg(s)
    slide_header(s, "How It Works", "All local. No external calls.")
    arch = (
        "ZONE SENSORS (×4)          EDGE BACKEND (laptop / edge box)\n"
        "  methane, CO, temp   →    MQTT broker (Mosquitto)\n"
        "  airflow, fan speed         ↓\n"
        "                             Trend detector + fan loop\n"
        "                             ↓\n"
        "                             FastAPI  /zones  /alert  /ask\n"
        "                             ↓\n"
        "                             Reg 854 docs + template answers\n"
        "                             ↓\n"
        "                             Web UI + voice alert (offline)"
    )
    box = s.shapes.add_textbox(Inches(0.9), Inches(1.7), Inches(7.5), Inches(4.8))
    tf = box.text_frame
    p = tf.paragraphs[0]
    p.text = arch
    p.font.name = "Courier New"
    p.font.size = Pt(14)
    p.font.color.rgb = WHITE
    add_bullets(s, 8.6, 1.9, 4.0, 4.5, [
        "Production: wireless self-healing mesh",
        "Demo: local MQTT on localhost",
        "Fallback: internal timer (no broker needed)",
    ], size=15, color=MUTED)

    # 6 — KEY DIFFERENTIATOR (Trend)
    s = prs.slides.add_slide(blank)
    set_slide_bg(s)
    slide_header(s, "Key Differentiator: TREND, Not Threshold", "The crew leaves before it's an emergency")
    add_textbox(s, 0.9, 1.7, 5.5, 1.0, "Traditional systems:", size=18, bold=True, color=RED)
    add_bullets(s, 0.9, 2.3, 5.5, 2.0, ["Alarm at 1.5% methane", "Reactive — too late for orderly withdrawal"], size=16)
    add_textbox(s, 7.0, 1.7, 5.5, 1.0, "MineGuard Edge:", size=18, bold=True, color=GREEN)
    add_bullets(s, 7.0, 2.3, 5.5, 2.5, [
        "Track last N readings per zone",
        "Flag rising methane at 0.9%+ → YELLOW",
        "Cross 1.5% → RED + cited evacuation procedure",
    ], size=16)
    add_textbox(s, 0.9, 5.2, 11.5, 1.2,
        "Status flow:  GREEN (stable)  →  YELLOW (rising)  →  RED (danger)  →  GREEN (ventilation restored)",
        size=16, color=ACCENT, align=PP_ALIGN.CENTER)

    # 7 — SMART VENTILATION (Act, not just alarm)
    s = prs.slides.add_slide(blank)
    set_slide_bg(s)
    slide_header(s, "Smart Ventilation Loop", "Detect → Act → Recover")
    add_bullets(s, 0.9, 1.7, 11.2, 4.8, [
        "Gas inrush detected → fan ramps from 20% idle toward maximum",
        "Increased airflow dilutes and sweeps methane out of the zone",
        "As gas clears, fan eases back — saves power underground",
        "Critical rule: we NEVER enrich oxygen (raises explosion risk)",
        "All-clear voice message when zone returns to green",
    ], size=18)
    add_textbox(s, 0.9, 5.8, 11, 0.8,
        "Safety actions at RED: max airflow · cut non-flameproof power · stop ignition work · evacuate",
        size=14, color=MUTED)

    # 8 — REG 854 COMPLIANCE
    s = prs.slides.add_slide(blank)
    set_slide_bg(s)
    slide_header(s, "Grounded in Regulation", "O. Reg 854 — Mines and Mining Plants")
    add_bullets(s, 0.9, 1.7, 11.2, 3.5, [
        "5 local Reg 854 text sections indexed offline",
        "Keyword retrieval — no cloud LLM required",
        "Every alert includes source citation (section + text)",
        "POST /ask — free-text safety questions answered from local docs",
    ], size=18)
    add_textbox(s, 0.9, 5.0, 11.5, 1.5,
        'Example: "Withdraw all persons from the affected area to a place of safety. '
        'Do not re-enter until gas levels are confirmed safe by a qualified person."',
        size=15, color=ACCENT)

    # 9 — TECH STACK
    s = prs.slides.add_slide(blank)
    set_slide_bg(s)
    slide_header(s, "Technology Stack", "Every component runs offline")
    rows = [
        ("Transport", "Mosquitto MQTT (mesh stand-in)"),
        ("Backend", "Python · FastAPI · paho-mqtt"),
        ("Intelligence", "Trend detector · template answers · optional Ollama"),
        ("Regulatory", "Local Reg 854 .txt retrieval"),
        ("Frontend", "Lovable → exported React (local dev server)"),
        ("Voice", "Browser Web Speech API (offline TTS)"),
    ]
    y = 1.8
    for label, value in rows:
        add_textbox(s, 0.9, y, 2.5, 0.4, label, size=16, bold=True, color=ACCENT)
        add_textbox(s, 3.5, y, 8.5, 0.4, value, size=16)
        y += 0.55

    # 10 — DEMO (most important category for judges)
    s = prs.slides.add_slide(blank)
    set_slide_bg(s)
    slide_header(s, "Live Demo — 60 Second Arc", "Show, don't tell")
    steps = [
        ("0:00", "Zone map all GREEN — normal shift underground"),
        ("0:15", "Zone 3 methane starts CLIMBING → YELLOW + rising arrow"),
        ("0:30", "Fan ramps · ventilation mitigation active"),
        ("0:40", "Crosses 1.5% → RED · banner fires · voice speaks Reg 854 procedure"),
        ("0:50", "Turn WIFI OFF · demo again · still works"),
        ("1:00", "Zone clears → all-clear voice: \"Zone 3 stabilized\""),
    ]
    y = 1.75
    for time, desc in steps:
        add_textbox(s, 0.9, y, 1.2, 0.35, time, size=14, bold=True, color=ACCENT)
        add_textbox(s, 2.2, y, 9.5, 0.35, desc, size=16)
        y += 0.55
    add_textbox(s, 0.9, 6.0, 11, 0.5, "Backup: pre-recorded demo video if live fails", size=12, color=MUTED)

    # 11 — BUILD TODAY vs PITCH
    s = prs.slides.add_slide(blank)
    set_slide_bg(s)
    slide_header(s, "What We Built vs. Production Vision", "Honest scope — judges respect this")
    add_textbox(s, 0.9, 1.7, 5.5, 0.4, "TODAY (3-hour build)", size=18, bold=True, color=GREEN)
    add_bullets(s, 0.9, 2.2, 5.5, 3.5, [
        "Simulated zones on one laptop",
        "Local MQTT or internal timer",
        "Full API + trend + ventilation loop",
        "Offline demo with wifi disabled",
    ], size=15)
    add_textbox(s, 7.0, 1.7, 5.5, 0.4, "PRODUCTION (the pitch)", size=18, bold=True, color=ACCENT)
    add_bullets(s, 7.0, 2.2, 5.5, 3.5, [
        "Real sensor node per zone",
        "Wireless self-healing mesh transport",
        "Edge box underground, sync at surface",
        "On-device TTS in cap lamp / tablet",
    ], size=15)

    # 12 — IMPACT
    s = prs.slides.add_slide(blank)
    set_slide_bg(s)
    slide_header(s, "Impact", "Why mining judges should care")
    add_bullets(s, 0.9, 1.7, 11.2, 4.5, [
        "Early warning → orderly withdrawal, not emergency evacuation",
        "Offline-first → works when comms are damaged during roof falls",
        "No central server → no single point of failure underground",
        "Cited procedures → auditable safety decisions for inspectors",
        "Same architecture major operators already deploy (mesh + MQTT + edge)",
    ], size=18)

    # 13 — TEAM
    s = prs.slides.add_slide(blank)
    set_slide_bg(s)
    slide_header(s, "Team", "Three roles, one vertical slice")
    roles = [
        ("Backend / Edge (B)", "MQTT · simulators · trend · FastAPI · Reg 854"),
        ("Frontend (F)", "Zone map · alerts · Lovable UI · local export"),
        ("Voice + Pitch (V)", "Web Speech API · demo script · this deck"),
    ]
    y = 2.0
    for role, desc in roles:
        add_textbox(s, 0.9, y, 4.0, 0.4, role, size=18, bold=True, color=ACCENT)
        add_textbox(s, 0.9, y + 0.45, 11.0, 0.4, desc, size=16)
        y += 1.1

    # 14 — CLOSE / CTA
    s = prs.slides.add_slide(blank)
    set_slide_bg(s)
    add_textbox(s, 0.9, 2.2, 11.5, 1.0, "MineGuard Edge", size=44, bold=True, align=PP_ALIGN.CENTER)
    add_textbox(
        s, 0.9, 3.3, 11.5, 1.0,
        "Get crews out before it's an emergency — offline, cited, and spoken.",
        size=20, color=ACCENT, align=PP_ALIGN.CENTER,
    )
    add_textbox(s, 0.9, 4.8, 11.5, 0.6, "Questions?", size=28, bold=True, align=PP_ALIGN.CENTER)
    add_textbox(s, 0.9, 5.8, 11.5, 0.5, "github.com/RavalDH/Cursor_Hack  ·  localhost:8000/docs", size=13, color=MUTED, align=PP_ALIGN.CENTER)

    prs.save(OUTPUT)
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    build()
