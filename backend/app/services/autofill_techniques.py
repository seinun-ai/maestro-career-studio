"""Technique cards for /step: how to work one KIND of widget, never one site.

A card is a few plain sentences about a widget kind (a search box, a multi-select, a
popup list...), appended to the step prompt for a field of that kind. It says nothing
about a site or a vendor: what is learned about one site is the recipe book's, kept in
the browser. Each card names only moves the page can offer (fill-core stepState:
click:oN, search:value, search:word:N, search:term, open, scroll, give_up). A card is
at most MAX_CARD characters because the prompt runs on every step.
"""

MAX_CARD = 700

CARDS: dict[str, str] = {
    "search": (
        "Results can arrive in stages: wait for the list, don't search again at once. If the full answer "
        "lists nothing, search one distinctive word of it (search:word:N), then a synonym or the broader "
        "category (search:term). Prefer an exact option; take the closest only when the list is complete. "
        "A move that changed nothing, or already ran twice, will not run again: try another or give up."
    ),
    "multi": (
        "Each item is its own search and click; a pill appearing is the proof. If an item's pill doesn't "
        "appear, click its row once more. If an item lists nothing, search one distinctive word of it, or "
        "a synonym (search:term). An item the list never offers is skipped, never replaced with an "
        "unrelated one."
    ),
    "popup": (
        "Open the list first (open). Long lists scroll: scroll before deciding the answer is missing. "
        "A row that opens a group leads to sub-options; open it only if the answer is inside. A list "
        "with a search box can be filtered with the answer's distinctive word (search:word:N)."
    ),
    "group": "Click the option whose text answers the question as worded. A lone checkbox is yes when ticked.",
    "select": "Choose the option whose text answers the question; never the placeholder.",
    "date": "Fill the parts the page shows (month, day, year) in its own format.",
}

assert all(len(card) <= MAX_CARD for card in CARDS.values())
