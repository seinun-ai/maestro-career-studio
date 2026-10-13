"""Base resume colours: the preset table and how a new resume gets one."""

import random

from app.services.resume_colors import PRESET_HUES, pick_hue


def test_presets_are_ten_distinct_hues_in_range():
    assert len(PRESET_HUES) == 10
    assert len(set(PRESET_HUES)) == 10
    assert all(0 <= h < 360 for h in PRESET_HUES)


def test_pick_avoids_hues_in_use():
    used = PRESET_HUES[:9]
    assert pick_hue(used, rng=random.Random(1)) == PRESET_HUES[9]


def test_pick_is_random_among_free_presets():
    seen = {pick_hue([], rng=random.Random(seed)) for seed in range(50)}
    assert len(seen) > 3
    assert seen <= set(PRESET_HUES)


def test_when_all_are_taken_pick_the_least_used():
    used = list(PRESET_HUES) + list(PRESET_HUES[1:])  # every preset twice except the first
    assert pick_hue(used, rng=random.Random(3)) == PRESET_HUES[0]


def test_custom_hues_in_use_do_not_block_presets():
    assert pick_hue([7, 41, 200], rng=random.Random(2)) in PRESET_HUES
