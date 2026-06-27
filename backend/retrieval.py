"""Offline keyword retrieval over the local Reg 854 documents.

This powers POST /ask. There is no embedding model and no network call — just a
keyword overlap score over a handful of local .txt files. For five short
regulation sections that's not only enough, it's preferable: it's instant,
deterministic, and trivially auditable, which is exactly what you want for
safety guidance at the edge.
"""

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from models import Citation

logger = logging.getLogger(__name__)

DOCS_DIR = Path(__file__).parent / "docs"

# Words too common to carry meaning; ignoring them keeps scoring honest so a
# question about "methane" isn't swamped by matches on "the" or "is".
_STOPWORDS = {
    "the", "a", "an", "is", "are", "of", "to", "in", "on", "for", "and", "or",
    "what", "when", "where", "how", "do", "i", "we", "should", "if", "at",
    "be", "it", "this", "that", "my", "with", "procedure", "reg", "section",
}


@dataclass
class Doc:
    """One loaded regulation section."""

    source: str  # e.g. "O. Reg 854 s.123 — Methane ..." (first line of the file)
    path: Path
    text: str
    tokens: set[str]


def _tokenize(text: str) -> set[str]:
    """Lowercase word set with stopwords removed — the unit of comparison."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


@lru_cache
def load_docs() -> list[Doc]:
    """Load and cache all docs/*.txt.

    Cached because the regulation text never changes at runtime; we pay the file
    reads once at first use. A missing docs/ folder is logged, not fatal — the
    rest of the system (zones, alerts) must keep working regardless.
    """
    docs: list[Doc] = []
    if not DOCS_DIR.is_dir():
        logger.warning("docs/ directory not found at %s — /ask will be empty", DOCS_DIR)
        return docs

    for path in sorted(DOCS_DIR.glob("*.txt")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not read doc %s: %s", path.name, exc)
            continue
        # The first non-empty line is the human-readable citation label.
        first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), path.stem)
        docs.append(Doc(source=first_line, path=path, text=text, tokens=_tokenize(text)))

    logger.info("Loaded %d Reg 854 document(s) for retrieval", len(docs))
    return docs


def _best_snippet(question_tokens: set[str], text: str) -> str:
    """Pick the most relevant paragraph from a doc to quote as the citation.

    We score each paragraph by how many question words it contains and return
    the best one, so the citation shown is the part that actually answers the
    question rather than the file's header.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return text.strip()

    # Drop the title line (first paragraph) and the NOTE disclaimer: neither is
    # quotable regulation text, and without this they can win on keyword overlap
    # and leave the citation showing only a header.
    candidates = [
        p for p in paragraphs[1:] if not p.lstrip().upper().startswith("NOTE:")
    ] or paragraphs

    def overlap(paragraph: str) -> int:
        return len(question_tokens & _tokenize(paragraph))

    best = max(candidates, key=overlap)
    # If nothing matched, fall back to the first substantive paragraph.
    if overlap(best) == 0:
        return candidates[0]
    return best


def search(question: str, top_k: int = 2) -> list[Citation]:
    """Return up to top_k citations whose text best matches the question."""
    docs = load_docs()
    if not docs:
        return []

    q_tokens = _tokenize(question)
    if not q_tokens:
        return []

    scored = [(len(q_tokens & doc.tokens), doc) for doc in docs]
    scored = [(score, doc) for score, doc in scored if score > 0]
    scored.sort(key=lambda pair: pair[0], reverse=True)

    citations: list[Citation] = []
    for _, doc in scored[:top_k]:
        snippet = _best_snippet(q_tokens, doc.text)
        citations.append(Citation(source=doc.source, text=snippet))
    return citations


def find_doc(filename: str) -> Doc | None:
    """Look up a loaded doc by file name (used by answers.py for citations)."""
    target = filename.lower()
    for doc in load_docs():
        if doc.path.name.lower() == target:
            return doc
    return None
