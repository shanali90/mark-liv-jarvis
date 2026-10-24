"""core/speech_gate.py - Gate actions against background noise, foreign speech, and unprompted tool calls.

Allow an action ONLY when:
  1. JARVIS is awake
  2. The transcript contains the assistant name or a wake phrase,
     OR we are inside an active conversation window of 25 s after the last accepted command or JARVIS's reply
  3. The main language of the transcript is one the owner uses (English, Urdu/Hindi, Sindhi).
"""
from __future__ import annotations

import re
import time
from typing import Tuple, Dict, Any, List

# Unicode ranges for scripts
_RE_JAPANESE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff\u4e00-\u9fff]")
_RE_CYRILLIC = re.compile(r"[\u0400-\u04ff]")
_RE_ARABIC_SCRIPT = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]")
_RE_DEVANAGARI = re.compile(r"[\u0900-\u097f]")

# Characteristic markers for foreign languages (German, Portuguese, Spanish, etc.)
_RE_SPANISH_PUNCT = re.compile(r"[¿¡]")
_RE_GERMAN_DIACRITICS = re.compile(r"[äöüßÄÖÜ]")

_GERMAN_WORDS = {
    "ja", "ist", "der", "die", "das", "und", "nicht", "ein", "eine", "einer",
    "irgendwo", "garage", "in", "den", "dem", "zu", "mit", "sich", "auf",
    "für", "aber", "wir", "sie", "hier", "kann", "bitte", "danke", "gut"
}

_PORTUGUESE_SPANISH_WORDS = {
    "futebol", "de", "rua", "qué", "que", "te", "ha", "dado", "jesús", "jesus",
    "para", "com", "não", "nao", "uma", "este", "por", "como", "mais", "pero",
    "está", "esta", "estoy", "voce", "você", "obrigado", "gracias"
}

_WAKE_PHRASES = (
    "jarvis", "hey jarvis", "ok jarvis", "okay jarvis", "hi jarvis",
    "wake up", "daddy's home",
    # Sindhi greetings / wake words
    "سائين شان علي", "سائين", "اسلام عليڪم", "سلام", "اٿو", "جاڳو",
    # Urdu/Hindi greetings / wake words
    "سنو", "جاگو", "کیا حال", "جی جاروس", "جاروس"
)


def get_allowed_languages() -> List[str]:
    """Retrieve allowed languages list from settings or return defaults."""
    from memory.config_manager import load_api_keys
    cfg = load_api_keys()
    allowed = cfg.get("allowed_languages")
    if isinstance(allowed, list) and allowed:
        return [str(lang).lower().strip() for lang in allowed]
    return ["en", "ur", "hi", "sd", "english", "urdu", "hindi", "sindhi"]


def detect_language_family(transcript: str) -> str:
    """Heuristic identification of transcript language family."""
    t = transcript.strip()
    if not t:
        return "unknown"

    # 1. Non-Latin scripts
    if _RE_JAPANESE.search(t):
        return "japanese"
    if _RE_CYRILLIC.search(t):
        return "cyrillic"
    if _RE_ARABIC_SCRIPT.search(t):
        return "urdu_sindhi_arabic_script"
    if _RE_DEVANAGARI.search(t):
        return "hindi_devanagari"

    # 2. Latin script language heuristics
    if _RE_SPANISH_PUNCT.search(t):
        return "spanish"
    if _RE_GERMAN_DIACRITICS.search(t):
        return "german"

    # Tokenize words
    words = [w.strip(".,!?:;\"'()[]{}/-").lower() for w in re.findall(r"\b[\w¿¡äöüßÄÖÜéèêàáíóúãõç]+\b", t)]
    if not words:
        return "unknown"

    # Check German stopwords match
    german_matches = [w for w in words if w in _GERMAN_WORDS]
    if len(german_matches) >= 2 or any(w in ("irgendwo", "garage") for w in words):
        return "german"

    # Check Portuguese / Spanish match
    pt_es_matches = [w for w in words if w in _PORTUGUESE_SPANISH_WORDS]
    if len(pt_es_matches) >= 2 or any(w in ("futebol", "jesús") for w in words):
        return "portuguese_or_spanish"

    # Default Latin script is accepted as English or Roman Urdu/Hindi/Sindhi
    return "english_or_roman_urdu_hindi_sindhi"


def decide_action_allowed(transcript: str, state: Dict[str, Any] | None = None) -> Tuple[bool, str]:
    """Decide whether a tool call triggered by transcript should proceed."""
    state = state or {}

    # 1. Check if JARVIS is awake
    if not state.get("is_awake", True):
        return False, "JARVIS is asleep"

    clean_t = (transcript or "").strip()
    low_t = clean_t.lower()

    # 2. Check wake phrase or active conversation window (25 s)
    asst_name = str(state.get("assistant_name", "JARVIS")).lower()
    has_wake_word = bool(asst_name in low_t or any(wp in low_t for wp in _WAKE_PHRASES))

    now = state.get("now", time.monotonic())
    last_cmd = state.get("last_command_time", 0.0)
    last_reply = state.get("last_reply_time", 0.0)
    last_accepted = state.get("last_accepted_command_time", 0.0)
    last_active = max(last_cmd, last_reply, last_accepted)

    inside_window = (now - last_active <= 25.0) if last_active > 0 else False
    if state.get("active_window") or state.get("in_conversation"):
        inside_window = True

    if not has_wake_word and not inside_window:
        return False, "No assistant name or wake phrase, and outside active 25s conversation window"

    # 3. Check language of transcript
    lang = detect_language_family(clean_t)

    allowed_settings = get_allowed_languages()
    is_lang_allowed = False

    if lang in ("english_or_roman_urdu_hindi_sindhi", "unknown"):
        if any(code in allowed_settings for code in ("en", "english", "ur", "urdu", "hi", "hindi", "sd", "sindhi")):
            is_lang_allowed = True
    elif lang in ("urdu_sindhi_arabic_script", "hindi_devanagari"):
        if any(code in allowed_settings for code in ("ur", "urdu", "sd", "sindhi", "hi", "hindi")):
            is_lang_allowed = True

    if not is_lang_allowed:
        return False, f"Transcript language '{lang}' is not an allowed language for owner commands"

    return True, "allowed"
