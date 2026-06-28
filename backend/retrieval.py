"""Offline keyword retrieval over the local Reg 854 docs — powers POST /ask.

No embeddings, no network: just keyword overlap over a handful of .txt files.
For a few short sections that's instant, deterministic, and auditable.
"""

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from models import Citation

logger = logging.getLogger(__name__)

DOCS_DIR = Path(__file__).parent / "docs"

# Common words dropped so scoring isn't swamped by "the"/"is".
_STOPWORDS = {
    "the", "a", "an", "is", "are", "of", "to", "in", "on", "for", "and", "or",
    "what", "when", "where", "how", "do", "i", "we", "should", "if", "at",
    "be", "it", "this", "that", "my", "with", "procedure", "reg", "section",
}


@dataclass
class Doc:
    """One loaded regulation section."""

    source: str  # first line of the file, the human citation label
    path: Path
    text: str
    tokens: set[str]


def _tokenize(text: str) -> set[str]:
    """Lowercase word set, stopwords removed — the unit of comparison."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


@lru_cache
def load_docs() -> list[Doc]:
    """Load and cache docs/*.txt. A missing folder is logged, not fatal."""
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
        # First non-empty line is the citation label.
        first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), path.stem)
        docs.append(Doc(source=first_line, path=path, text=text, tokens=_tokenize(text)))

    logger.info("Loaded %d Reg 854 document(s) for retrieval", len(docs))
    return docs


def _best_snippet(question_tokens: set[str], text: str) -> str:
    """Pick the paragraph with the most question-word overlap to quote as the citation."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return text.strip()

    # Skip the title and NOTE disclaimer — neither is quotable regulation text.
    candidates = [
        p for p in paragraphs[1:] if not p.lstrip().upper().startswith("NOTE:")
    ] or paragraphs

    def overlap(paragraph: str) -> int:
        return len(question_tokens & _tokenize(paragraph))

    best = max(candidates, key=overlap)
    # Nothing matched -> first substantive paragraph.
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
