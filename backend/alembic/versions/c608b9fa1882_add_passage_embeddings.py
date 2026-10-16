"""add passage embeddings

Revision ID: c608b9fa1882
Revises: 881be666508b
Create Date: 2026-10-15 12:12:36.679977

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = 'c608b9fa1882'
down_revision: Union[str, Sequence[str], None] = '881be666508b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # The pgvector extension must exist before a column can use the `vector` type.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # 384 = output size of bge-small-en-v1.5. NULL until the paper is indexed.
    op.add_column("passages", sa.Column("embedding", Vector(384), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("passages", "embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")
