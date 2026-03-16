"""steps_ranges_string_to_json

Revision ID: a6f1add50e1f
Revises: 27a78d504300
Create Date: 2026-03-15 17:37:20.876825

"""
import json

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a6f1add50e1f'
down_revision = '27a78d504300'
branch_labels = None
depends_on = None


def _parse_ranges_string(s: str) -> list[list[int]]:
    """Convert '0-20, 30' → [[0, 20], [30, 30]]."""
    result = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            result.append([int(start), int(end)])
        else:
            idx = int(part)
            result.append([idx, idx])
    return result


def upgrade():
    conn = op.get_bind()

    # Convert existing string values to valid JSON while column is still VARCHAR
    rows = conn.execute(sa.text("SELECT uid, id, steps_ranges FROM album")).fetchall()
    for uid, aid, raw in rows:
        parsed = _parse_ranges_string(raw) if isinstance(raw, str) else raw
        conn.execute(
            sa.text("UPDATE album SET steps_ranges = :val WHERE uid = :uid AND id = :aid"),
            {"val": json.dumps(parsed), "uid": uid, "aid": aid},
        )

    # Now all values are valid JSON strings — the USING cast will succeed
    op.alter_column(
        "album",
        "steps_ranges",
        type_=sa.JSON(),
        existing_type=sa.String(255),
        existing_nullable=False,
        postgresql_using="steps_ranges::json",
    )


def downgrade():
    conn = op.get_bind()

    rows = conn.execute(sa.text("SELECT uid, id, steps_ranges FROM album")).fetchall()

    op.alter_column(
        "album",
        "steps_ranges",
        type_=sa.String(255),
        existing_type=sa.JSON(),
        existing_nullable=False,
    )

    for uid, aid, raw in rows:
        if isinstance(raw, list):
            parts = []
            for r in raw:
                if r[0] == r[1]:
                    parts.append(str(r[0]))
                else:
                    parts.append(f"{r[0]}-{r[1]}")
            val = ", ".join(parts)
        else:
            val = str(raw)
        conn.execute(
            sa.text("UPDATE album SET steps_ranges = :val WHERE uid = :uid AND id = :aid"),
            {"val": val, "uid": uid, "aid": aid},
        )
