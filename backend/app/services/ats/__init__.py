from app.services.ats.config import ENGINE_VERSION, AtsConfig, load_config
from app.services.ats.engine import AtsResult, score_resume
from app.services.ats.matching import SkillMatcher, normalize_term, term_in_text

# The declared interface IS the consumed interface: SkillMatcher/normalize_term/
# term_in_text are used by gap_analysis, kb_resolver, tailoring_session and the
# explore builders, so they are exported here rather than reached via submodule
# paths. embeddings stays a submodule import on purpose — its model load is
# heavy and every consumer imports it lazily.
__all__ = [
    "ENGINE_VERSION",
    "AtsConfig",
    "AtsResult",
    "SkillMatcher",
    "load_config",
    "normalize_term",
    "score_resume",
    "term_in_text",
]
