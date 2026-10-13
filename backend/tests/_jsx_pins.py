"""Small readers for the source pins on JSX: an opening tag, and a class attribute's tokens."""

import re


def squash(src: str) -> str:
    return " ".join(src.split())


def _step(c: str, quote: str, depth: int) -> tuple[str, int]:
    """One character of a JSX opening tag: the quote it is inside (if any) and the brace depth after it."""
    if quote:
        return ("" if c == quote else quote), depth
    return (c if c in "\"'`" else ""), depth + {"{": 1, "}": -1}.get(c, 0)


def open_tag(src: str, name: str, after: str = "") -> str:
    """The first `<name ...>` opening tag at or after `after`, through its closing `>`, skipping braces and quotes."""
    found = re.compile(rf"<{re.escape(name)}(?=[\s/>])").search(src, src.index(after) if after else 0)
    assert found, f"no <{name}> after {after!r}"
    quote, depth = "", 0
    for i in range(found.start(), len(src)):
        quote, depth = _step(src[i], quote, depth)
        if src[i] == ">" and depth == 0 and not quote and src[i - 1] != "=":
            return squash(src[found.start() : i + 1])
    raise AssertionError(f"unterminated <{name}")


def tokens(tag: str, attr: str = "className") -> set[str]:
    """The class tokens of a tag's `attr="..."` (a plain string literal)."""
    start = tag.index(f'{attr}="') + len(attr) + 2
    return set(tag[start : tag.index('"', start)].split())
