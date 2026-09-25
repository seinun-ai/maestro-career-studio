"""Re-seed health defaults only when the stored prompt still equals the old default."""
from alembic import op
import sqlalchemy as sa

revision = "d08dd68e4eff"
down_revision = "980498217fe6"
branch_labels = None
depends_on = None

OLD_RESUME_BULLET_CLASSIFY = 'You are classifying resume bullet points (and the summary) onto a 5-level evidence ladder.\nJudge ONLY what the text establishes. Do not reward adjectives. Do not do arithmetic.\n\nLevels:\n- "direct": strong ownership verb + specific scope + a quantified OUTCOME (%, $, time saved,\n  rate, delta). The number measures a result, not just size.\n- "analogue": strong ownership verb + a concrete SCALE metric (rows, users, requests, latency,\n  criteria, rank). Real, checkable evidence — but the number measures the thing, not the outcome.\n- "adjacent": strong verb + specific technical scope, but NO genuine number.\n- "implied": vague or team-level; the reader cannot tell what this person actually did.\n- "unaddressed": a duty statement or weak opener ("Responsible for", "Worked on", "Helped").\n\nWhat counts as a genuine metric: a digit paired with a unit, magnitude, or scale noun.\nNOT a metric: a year (2024), a version (Python 3, Airflow 2.8), a GPA. "Built a pipeline using\nSpark 3.5" has NO metric.\n\nEach item may carry deterministic hints: "weak_opener" (starts with a duty phrase) or\n"passive" (passive-voice opening). Treat a weak_opener hint as strong evidence for\n"unaddressed" unless the rest of the text clearly establishes ownership and evidence.\n\nConfidence: 0.0-1.0. If you genuinely cannot decide between two adjacent levels, pick the LOWER\none and set confidence below 0.6 — the system turns low confidence into a question for the\ncandidate instead of a guess.\n\nItems (JSON): $items_json\n\nReturn JSON only — an object whose "classifications" value is a JSON array with\none entry per input item, each entry shaped exactly:\n  {"id": "<item id>", "level": "<one of the five>", "reason": "<= 12 words>", "confidence": 0.0}\nReturn exactly one entry per input item, same ids.\n'


def upgrade() -> None:
    op.execute(sa.text("DELETE FROM settings WHERE key = :key AND value = :old").bindparams(
        key="prompt.resume_bullet_classify", old=OLD_RESUME_BULLET_CLASSIFY))


def downgrade() -> None:
    """No-op: restoring an old prompt could overwrite a user's new customization."""
