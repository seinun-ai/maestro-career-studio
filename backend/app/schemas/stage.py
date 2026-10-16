"""The rung vocabulary of services/stage.py, in a leaf module so the schemas never import the
services layer."""

from typing import Literal, get_args

Rung = Literal["saved", "scored", "gaps", "tailored", "pdf_ready", "applied", "closed"]
RUNGS = get_args(Rung)
