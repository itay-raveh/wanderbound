"""maps_ranges_string_to_json

Revision ID: c4d9e1f23a77
Revises: b3e2f7c81d44
Create Date: 2026-03-15 21:00:00.000000

"""
import json
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from zoneinfo import ZoneInfo


revision = 'c4d9e1f23a77'
down_revision = 'b3e2f7c81d44'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    albums = conn.execute(sa.text(
        "SELECT uid, id, maps_ranges FROM album"
    )).fetchall()

    # Convert existing string values to JSON before altering column
    for uid, aid, raw in albums:
        if raw is None or raw == "":
            val = json.dumps([])
        elif isinstance(raw, str):
            # Parse "0-20, 30" format, map indices to dates via step table
            steps = conn.execute(sa.text(
                "SELECT idx, timestamp, timezone_id FROM step "
                "WHERE uid = :uid AND aid = :aid ORDER BY idx"
            ), {"uid": uid, "aid": aid}).fetchall()

            if not steps:
                val = json.dumps([])
            else:
                date_ranges = []
                for part in raw.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    if "-" in part:
                        start_idx, end_idx = part.split("-", 1)
                        start_idx, end_idx = int(start_idx), int(end_idx)
                    else:
                        start_idx = end_idx = int(part)

                    from_step = next((s for s in steps if s[0] == start_idx), None)
                    to_step = next((s for s in steps if s[0] == end_idx), None)
                    if not from_step or not to_step:
                        continue
                    from_date = datetime.fromtimestamp(
                        from_step[1], tz=ZoneInfo(from_step[2])
                    ).date().isoformat()
                    to_date = datetime.fromtimestamp(
                        to_step[1], tz=ZoneInfo(to_step[2])
                    ).date().isoformat()
                    date_ranges.append([from_date, to_date])
                val = json.dumps(date_ranges)
        else:
            val = json.dumps(raw)

        conn.execute(
            sa.text("UPDATE album SET maps_ranges = :val WHERE uid = :uid AND id = :aid"),
            {"val": val, "uid": uid, "aid": aid},
        )

    op.alter_column(
        "album",
        "maps_ranges",
        type_=sa.JSON(),
        existing_type=sa.String(255),
        existing_nullable=True,
        nullable=False,
        server_default="[]",
        postgresql_using="maps_ranges::json",
    )


def downgrade():
    conn = op.get_bind()

    albums = conn.execute(sa.text(
        "SELECT uid, id, maps_ranges FROM album"
    )).fetchall()

    op.alter_column(
        "album",
        "maps_ranges",
        type_=sa.String(255),
        existing_type=sa.JSON(),
        existing_nullable=False,
        nullable=True,
    )

    # Best-effort downgrade: maps_ranges as date pairs can't map back to indices
    # without steps context, so just clear them
    for uid, aid, _raw in albums:
        conn.execute(
            sa.text("UPDATE album SET maps_ranges = NULL WHERE uid = :uid AND id = :aid"),
            {"uid": uid, "aid": aid},
        )
