"""Every action answers (visual-language plan, Wave 2).

The Button primitive owns its loading state: `pending` shows a spinner, keeps the button focusable and
busy, and ignores presses. Base UI marks a disabled button `data-disabled`, which the primitive styles
itself, so call sites stop repeating the class by hand.
"""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def test_the_button_has_a_pending_state():
    src = _read("components/ui/button.tsx")
    assert "pending?: boolean" in src
    assert "aria-busy={pending || undefined}" in src
    assert "focusableWhenDisabled" in src and "Loader2" in src


def test_the_button_styles_data_disabled_itself():
    src = _read("components/ui/button.tsx")
    assert "data-disabled:pointer-events-none" in src and "data-disabled:opacity-50" in src
