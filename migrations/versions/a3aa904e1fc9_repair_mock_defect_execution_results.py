"""repair mock defect execution results

Revision ID: a3aa904e1fc9
Revises: 9122e14c70bb
Create Date: 2026-07-11 21:50:56.958879

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'a3aa904e1fc9'
down_revision = '9122e14c70bb'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE test_execution
        SET result = 'failed',
            actual_result = COALESCE(
                NULLIF(TRIM(actual_result), ''),
                'Sample defect-related failed result.'
            ),
            updated_at = CURRENT_TIMESTAMP
        WHERE id IN (
            SELECT DISTINCT test_execution_id
            FROM defect
        )
          AND result <> 'failed'
        """
    )
    op.execute(
        """
        UPDATE defect
        SET environment_snapshot = (
                SELECT test_execution.environment
                FROM test_execution
                WHERE test_execution.id = defect.test_execution_id
            ),
            actual_result_snapshot = (
                SELECT test_execution.actual_result
                FROM test_execution
                WHERE test_execution.id = defect.test_execution_id
            ),
            executed_at_snapshot = (
                SELECT test_execution.executed_at
                FROM test_execution
                WHERE test_execution.id = defect.test_execution_id
            ),
            updated_at = CURRENT_TIMESTAMP
        """
    )


def downgrade():
    # The original result cannot be reconstructed without corrupting valid failed data.
    pass
