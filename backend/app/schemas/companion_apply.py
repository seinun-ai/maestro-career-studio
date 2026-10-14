"""The Companion's Apply switches. Two yes/no choices read by the panel when it binds a tab.

- `auto_pick`: the panel chooses the base resume for the user, but only on a clear win (a top match
  score at or above Auto-apply's floor, ahead of the next by its margin). Off: nothing is preselected.
- `stop_each_step`: Apply stops after saving the job, after the resume, and before filling, so the
  user presses once per step.
"""
from pydantic import BaseModel, StrictBool


class CompanionApplySettings(BaseModel):
    auto_pick: StrictBool = True
    stop_each_step: StrictBool = False
