"""Shared Google Photos domain types.

Type aliases used across models, logic, and services layers.
Constrained string types provide runtime validation via Pydantic.
"""

from typing import Annotated

from pydantic import StringConstraints

type GoogleMediaId = Annotated[str, StringConstraints(max_length=256)]
type MediaFilename = Annotated[str, StringConstraints(pattern=r"^[^/\\\x00]+$")]
