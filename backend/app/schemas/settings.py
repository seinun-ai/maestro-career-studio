"""Request and response shapes for /api/settings/*.

One envelope, not one payload class per setting. `AutofillProfilePayload`,
`QuickTailorProfilePayload` and `McpWorkflowPayload` used to be three separate
names for the identical `value: dict[str, Any]`, and the four typed settings
each had their own single-field wrapper. A generic carries all of them and,
unlike a bare dict return, gives every endpoint a `response_model` — 16 of the
26 settings routes previously had none, so they were untyped in the OpenAPI
schema even where a perfectly good model existed.
"""

from typing import Any

from pydantic import BaseModel


class SettingEnvelope[T](BaseModel):
    """`{"key": ..., "value": ...}` — the shape every blob endpoint speaks."""

    key: str
    value: T


class SettingValueIn[T](BaseModel):
    """Request body: the envelope without the key, which the path already says."""

    value: T


class TextSettingPayload(BaseModel):
    value: str


class PromptPayload(BaseModel):
    value: str


class SettingValue(BaseModel):
    key: str
    value: str


# The autofill profile stays an untyped dict on purpose: the browser extension
# treats every field as optional and ships on its own release cadence, so the
# shape is deliberately loose (see services/autofill_profile.py).
AutofillProfilePayload = SettingValueIn[dict[str, Any]]
