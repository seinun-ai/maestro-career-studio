"""Base resume colours.

A base resume's colour is identity, never state: one hue per resume, shown as a
square beside its name. The app derives every tone from the hue (see
frontend/lib/resume-color.ts and globals.css), so only the hue is stored.

PRESET_HUES is mirrored in frontend/lib/resume-color.ts and
extension/shared/resume-color.js; test_resume_color_parity.py pins all three.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Iterable

PRESET_HUES: tuple[int, ...] = (5, 40, 80, 125, 160, 195, 230, 265, 300, 335)


def valid_hue(value: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 360


def pick_hue(used: Iterable[int | None], *, rng: random.Random | None = None) -> int:
    """A random preset no resume in `used` has; else one of the least-used presets."""
    rng = rng or random.Random()
    counts = Counter(h for h in used if h in PRESET_HUES)
    fewest = min(counts.get(h, 0) for h in PRESET_HUES)
    return rng.choice([h for h in PRESET_HUES if counts.get(h, 0) == fewest])
