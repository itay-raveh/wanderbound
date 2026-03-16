"""steps_ranges_index_to_date

Revision ID: b3e2f7c81d44
Revises: a6f1add50e1f
Create Date: 2026-03-15 20:00:00.000000

"""
import json
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from zoneinfo import ZoneInfo


# revision identifiers, used by Alembic.
revision = 'b3e2f7c81d44'
down_revision = 'a6f1add50e1f'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    albums = conn.execute(sa.text(
        "SELECT uid, id, steps_ranges FROM album"
    )).fetchall()

    for uid, aid, ranges in albums:
        if not isinstance(ranges, list) or not ranges:
            continue

        # Load all steps for this album, ordered by idx
        steps = conn.execute(sa.text(
            "SELECT idx, timestamp, timezone_id FROM step "
            "WHERE uid = :uid AND aid = :aid ORDER BY idx"
        ), {"uid": uid, "aid": aid}).fetchall()

        if not steps:
            continue

        date_ranges = []
        for start_idx, end_idx in ranges:
            # Find step rows by index
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

        conn.execute(
            sa.text("UPDATE album SET steps_ranges = :val WHERE uid = :uid AND id = :aid"),
            {"val": json.dumps(date_ranges), "uid": uid, "aid": aid},
        )


def downgrade():
    conn = op.get_bind()

    albums = conn.execute(sa.text(
        "SELECT uid, id, steps_ranges FROM album"
    )).fetchall()

    for uid, aid, ranges in albums:
        if not isinstance(ranges, list) or not ranges:
            continue

        steps = conn.execute(sa.text(
            "SELECT idx, timestamp, timezone_id FROM step "
            "WHERE uid = :uid AND aid = :aid ORDER BY idx"
        ), {"uid": uid, "aid": aid}).fetchall()

        if not steps:
            continue

        # Build date→idx lookup (first/last step on each date)
        from collections import defaultdict
        by_date = defaultdict(list)
        for idx, ts, tz_id in steps:
            d = datetime.fromtimestamp(ts, tz=ZoneInfo(tz_id)).date().isoformat()
            by_date[d].append(idx)

        index_ranges = []
        for from_date, to_date in ranges:
            from_indices = by_date.get(from_date, [])
            to_indices = by_date.get(to_date, [])
            if from_indices and to_indices:
                index_ranges.append([min(from_indices), max(to_indices)])

        conn.execute(
            sa.text("UPDATE album SET steps_ranges = :val WHERE uid = :uid AND id = :aid"),
            {"val": json.dumps(index_ranges), "uid": uid, "aid": aid},
        )
