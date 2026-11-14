"""Initial PostGIS extension setup

Revision ID: 0001_initial_postgis_setup
Revises:
Create Date: 2026-11-14 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_postgis_setup"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enable PostGIS extension if available
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")


def downgrade() -> None:
    # Preserve a possibly pre-existing extension used by other schemas.
    pass
