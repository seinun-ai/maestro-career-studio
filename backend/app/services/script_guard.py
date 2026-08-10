import unicodedata

UNSUPPORTED_SCRIPT_KEYWORDS = {
    "CYRILLIC",
    "CJK",
    "HIRAGANA",
    "KATAKANA",
    "HANGUL",
    "ARABIC",
    "HEBREW",
    "DEVANAGARI",
    "THAI",
    "LAO",
}

MIN_NON_LATIN_CHAR_COUNT = 8
MIN_NON_LATIN_RATIO = 0.10


class UnsupportedScriptError(ValueError):
    """Raised when input text predominantly uses a script the pipeline cannot serve."""

    pass


def _script_name(char_name: str) -> str:
    for keyword in UNSUPPORTED_SCRIPT_KEYWORDS:
        if keyword in char_name:
            return keyword
    return "NON_LATIN"


def _dominant_script(script_counts: dict[str, int]) -> str:
    if not script_counts:
        return "Non-Latin"
    dominant = max(script_counts.items(), key=lambda item: item[1])[0]
    if dominant in ("CJK", "HIRAGANA", "KATAKANA", "HANGUL"):
        return "CJK"
    return dominant.capitalize()


def _count_non_latin(letters: list[str]) -> tuple[int, dict[str, int]]:
    counts: dict[str, int] = {}
    non_latin = 0
    for ch in letters:
        char_name = unicodedata.name(ch, "")
        if not char_name.startswith("LATIN"):
            non_latin += 1
            key = _script_name(char_name)
            counts[key] = counts.get(key, 0) + 1
    return non_latin, counts


def detect_unsupported_script(text: str) -> str | None:
    """Detect if text contains a significant portion of non-Latin script characters.

    Returns the name of the dominant non-Latin script (e.g. 'CJK', 'Cyrillic', 'Arabic'),
    or None if the text uses Latin script (including accented Latin like Zürich, José, Nestlé).
    """
    if not text:
        return None

    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return None

    non_latin, script_counts = _count_non_latin(letters)
    total = len(letters)
    if non_latin < MIN_NON_LATIN_CHAR_COUNT or (non_latin / total) < MIN_NON_LATIN_RATIO:
        return None

    return _dominant_script(script_counts)


def validate_script(text: str, source_label: str = "input") -> None:
    """Validate that text does not predominantly use an unsupported non-Latin script.

    Raises UnsupportedScriptError (ValueError subclass) if an unsupported script is detected.
    Accented Latin characters (e.g. Zürich, José, Nestlé, São Paulo) are explicitly permitted.
    """
    unsupported = detect_unsupported_script(text)
    if unsupported:
        raise UnsupportedScriptError(
            f"Unsupported script detected ({unsupported}) in {source_label}. "
            "Maestro CS currently supports English resumes and job descriptions using Latin script "
            "(including accented Latin characters such as Zürich, José, Nestlé, or São Paulo). "
            "Non-Latin scripts are not supported yet and are refused to avoid unreliable scoring."
        )


def extract_text_for_script_check(data: object) -> str:
    """Recursively collect text strings from nested dicts/lists for script checking."""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        return " ".join(extract_text_for_script_check(v) for v in data.values())
    if isinstance(data, list):
        return " ".join(extract_text_for_script_check(v) for v in data)
    return ""

