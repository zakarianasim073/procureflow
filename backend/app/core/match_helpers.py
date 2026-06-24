from difflib import SequenceMatcher
import re


def normalize_code(code: str) -> str:
    return "".join((code or "").split()).upper()


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    stop = {
        "complete", "works", "work", "including", "etc",
        "as", "per", "direction", "engineer", "in", "charge",
        "supply", "and", "installation", "of", "the", "a",
    }
    return " ".join(w for w in text.split() if w not in stop)


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()
