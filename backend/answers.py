"""Template Reg 854 procedures — fully offline, NO LLM.

Every answer here is a fixed, human-written sentence mapped to a (gas type +
severity) pair, paired with a citation whose *text* is pulled live from the
matching local .txt file. This is the PLAN's deliberate choice (section 5):
template answers are instant, reliable, and never hallucinate — which is the
only acceptable behaviour for safety guidance. A wrong "creative" answer
underground could get someone killed.
"""

import logging

from config import Settings
from models import Citation, Status
from retrieval import _best_snippet, _tokenize, find_doc, search

logger = logging.getLogger(__name__)

# Which document grounds each metric's procedure.
_METRIC_DOC = {
    "methane": "reg854_methane.txt",
    "co": "reg854_carbon_monoxide.txt",
    "no2": "reg854_post_blast_reentry.txt",
    "o2": "reg854_oxygen.txt",
    "co2": "reg854_ventilation.txt",
}

# Fixed procedure text per (metric, status). Written in plain imperative voice
# because in an alert the crew needs an action, not a paragraph.
_PROCEDURES: dict[tuple[str, Status], str] = {
    ("methane", "yellow"): (
        "Methane is elevated and climbing in this zone. Notify the supervisor, "
        "investigate and correct the cause, and increase ventilation to dilute "
        "and carry away the gas. Stop any drilling, blasting, or other "
        "ignition-capable work until levels fall."
    ),
    ("methane", "red"): (
        "Methane has reached the danger threshold. Withdraw all workers from the "
        "affected area to fresh air, barricade the area against entry, and "
        "de-energize non-flameproof electrical equipment. Do not resume work "
        "until the concentration is reduced and a supervisor declares the area "
        "safe."
    ),
    ("co", "yellow"): (
        "Carbon monoxide is elevated. Treat it as a possible fire or running "
        "engine in a confined space: identify the source, increase ventilation, "
        "and notify the supervisor immediately."
    ),
    ("co", "red"): (
        "Carbon monoxide has reached a dangerous level. Workers must don escape "
        "respirators and withdraw to fresh air. Ventilate and re-test the area "
        "before anyone re-enters."
    ),
    ("no2", "yellow"): (
        "Nitrogen dioxide is elevated — typical of post-blast fumes or diesel "
        "exhaust. Hold re-entry, increase ventilation to clear the heading, and "
        "notify the supervisor."
    ),
    ("no2", "red"): (
        "Nitrogen dioxide has reached a dangerous level. Do not enter the "
        "affected heading. Keep the crew out, ventilate fully, and re-test before "
        "anyone re-enters — NO2 is acutely toxic at low concentrations."
    ),
    ("o2", "yellow"): (
        "Oxygen is below the normal level in this level's air. Treat as an "
        "oxygen-deficiency warning: increase ventilation, identify what is "
        "displacing or consuming the oxygen, and notify the supervisor."
    ),
    ("o2", "red"): (
        "Oxygen is dangerously low. Do not enter without supplied-air breathing "
        "apparatus. Withdraw any workers, ventilate the level, and re-test before "
        "re-entry — an oxygen-deficient atmosphere can incapacitate in seconds."
    ),
}

# Keywords used to quote the most relevant clause from each doc as the citation.
_SNIPPET_KEYWORDS: dict[tuple[str, Status], str] = {
    ("methane", "yellow"): "notified investigated ventilation increased dilute",
    ("methane", "red"): "withdrawn barricaded de-energized declared safe",
    ("co", "yellow"): "increased source notified ventilation",
    ("co", "red"): "respirators withdraw fresh air re-tested",
    ("no2", "yellow"): "nitrogen dioxide blast fumes ventilation re-entry",
    ("no2", "red"): "nitrogen dioxide withdraw ventilate re-tested toxic",
    ("o2", "yellow"): "oxygen deficiency ventilation displaced",
    ("o2", "red"): "oxygen deficient supplied air withdraw re-test",
}


def procedure_for(
    metric: str, status: Status, settings: Settings
) -> tuple[str, list[Citation]]:
    """Return the fixed procedure + citation for a metric at a given severity.

    Used by GET /alert. Falls back gracefully if a doc is missing so an alert
    still carries useful text even if the citation can't be loaded.
    """
    answer = _PROCEDURES.get(
        (metric, status),
        "Monitor the zone, notify the supervisor, and follow the site's "
        "ventilation and gas-control procedures.",
    )

    citations: list[Citation] = []
    doc_name = _METRIC_DOC.get(metric)
    if doc_name:
        doc = find_doc(doc_name)
        if doc:
            keywords = _SNIPPET_KEYWORDS.get((metric, status), metric)
            snippet = _best_snippet(_tokenize(keywords), doc.text)
            citations.append(Citation(source=doc.source, text=snippet))
        else:
            logger.warning("Citation doc %s not found for %s alert", doc_name, metric)

    return answer, citations


# Keyword -> canned guidance for the free-text /ask endpoint. Order matters:
# the first topic whose keyword appears in the question wins.
_ASK_TOPICS: list[tuple[tuple[str, ...], str]] = [
    (
        ("methane", "ch4", "flammable", "explosive"),
        "For methane: at 1.0% notify the supervisor and increase ventilation; "
        "stop ignition-capable work as levels climb; at the danger threshold "
        "withdraw workers, barricade the area, and de-energize non-flameproof "
        "equipment until a supervisor declares it safe.",
    ),
    (
        ("co", "carbon", "monoxide", "fire", "diesel"),
        "For carbon monoxide: increase ventilation and find the source early, "
        "treat a rising trend as a possible fire, and at dangerous levels don "
        "escape respirators and withdraw to fresh air before re-testing.",
    ),
    (
        ("blast", "re-entry", "reentry", "re-enter", "post-blast", "clear", "clearance"),
        "After a blast, hold re-entry until the air clears. Carbon monoxide and "
        "nitrogen dioxide are the governing gases and CO clears slowest, so use "
        "CO falling back below its limit (with NO2 also clear) as the re-entry "
        "criterion. Ramp ventilation to shorten clearance time, and confirm with "
        "the fixed monitor before sending the crew back to the face.",
    ),
    (
        ("no2", "nitrogen", "dioxide", "nox", "fumes"),
        "For nitrogen dioxide: it is acutely toxic at low ppm and is a classic "
        "post-blast and diesel-exhaust gas. Hold re-entry, ventilate the heading, "
        "and re-test before entry; never rely on smell, as NO2 can be dangerous "
        "below the level it can be detected by odour.",
    ),
    (
        ("oxygen", "o2", "deficiency", "deficient", "asphyxiant"),
        "For oxygen: normal air is about 20.9%. Below ~19.5% is an oxygen-"
        "deficiency warning and below ~18% is dangerous. Increase ventilation, "
        "find what is displacing or consuming the oxygen, and never enter a "
        "deficient atmosphere without supplied-air breathing apparatus.",
    ),
    (
        ("airflow", "ventilation", "air", "fan"),
        "For ventilation: each zone needs enough fresh air to dilute hazardous "
        "gases; if airflow falls below plan, stop gas-generating work until "
        "adequate airflow is restored. Falling airflow often precedes rising "
        "gas, so treat them as one developing hazard.",
    ),
    (
        ("withdraw", "evacuate", "evacuation", "leave", "dangerous"),
        "When a place becomes dangerous: withdraw workers to a safe location "
        "first, barricade the area against entry, and only re-enter to correct "
        "the condition under a supervisor's direction. Resume work only after "
        "the place is examined and declared safe.",
    ),
    (
        ("test", "testing", "measure", "monitor", "calibrate", "trend"),
        "Test the atmosphere as often as needed with calibrated, appropriate "
        "instruments, and record the results. A sequence of readings — not a "
        "single number — is what reveals a zone trending toward danger.",
    ),
]


def answer_question(question: str) -> tuple[str, list[Citation]]:
    """Answer a free-text question with a template + retrieved citations.

    Strategy: pick a canned answer by topic keyword (deterministic and safe),
    and attach citations from the keyword search over docs/ so the user can see
    the regulation the answer rests on.
    """
    lowered = question.lower()
    answer = (
        "Follow the site's gas-control and ventilation procedures and notify "
        "your supervisor. See the cited Reg 854 sections for the specific limits "
        "and required actions."
    )
    for keywords, text in _ASK_TOPICS:
        if any(kw in lowered for kw in keywords):
            answer = text
            break

    citations = search(question)
    return answer, citations
