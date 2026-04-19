"""Google Photos domain types.

Constrained string type for Google media IDs, validated via Pydantic.
"""

from typing import Annotated

from pydantic import StringConstraints

type GoogleMediaId = Annotated[str, StringConstraints(max_length=256)]
