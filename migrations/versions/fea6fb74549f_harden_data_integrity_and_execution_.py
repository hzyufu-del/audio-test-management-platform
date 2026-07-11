"""harden data integrity and execution snapshots

Revision ID: fea6fb74549f
Revises: 5013098feed9
Create Date: 2026-07-10 19:40:41.749659

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fea6fb74549f'
down_revision = '5013098feed9'
branch_labels = None
depends_on = None


def set_sqlite_foreign_keys(enabled):
    connection = op.get_bind()
    if connection.dialect.name != 'sqlite':
        return

    value = 'ON' if enabled else 'OFF'
    with op.get_context().autocommit_block():
        connection.exec_driver_sql(f'PRAGMA foreign_keys={value}')


def check_sqlite_foreign_keys():
    connection = op.get_bind()
    if connection.dialect.name != 'sqlite':
        return

    violations = connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall()
    if violations:
        raise RuntimeError(f'Foreign key violations after migration: {violations}')


def upgrade():
    set_sqlite_foreign_keys(False)

    op.execute("UPDATE version SET status = 'planned' WHERE status = 'planning'")
    op.execute(
        """
        UPDATE test_case
        SET steps = 'Sample legacy test steps were not available.'
        WHERE steps IS NULL OR TRIM(steps) = ''
        """
    )
    op.execute(
        """
        UPDATE test_case
        SET expected_result = 'Sample legacy expected result was not available.'
        WHERE expected_result IS NULL OR TRIM(expected_result) = ''
        """
    )

    with op.batch_alter_table('test_execution', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('test_case_code_snapshot', sa.String(length=80), nullable=True)
        )
        batch_op.add_column(
            sa.Column('test_case_title_snapshot', sa.String(length=200), nullable=True)
        )
        batch_op.add_column(sa.Column('precondition_snapshot', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('steps_snapshot', sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column('expected_result_snapshot', sa.Text(), nullable=True)
        )

    op.execute(
        """
        UPDATE test_execution
        SET test_case_code_snapshot = COALESCE(
                (SELECT NULLIF(TRIM(test_case.code), '')
                 FROM test_case
                 WHERE test_case.id = test_execution.test_case_id),
                'MOCK-TESTCASE-' || test_execution.id
            ),
            test_case_title_snapshot = COALESCE(
                (SELECT NULLIF(TRIM(test_case.title), '')
                 FROM test_case
                 WHERE test_case.id = test_execution.test_case_id),
                'Sample legacy test case'
            ),
            precondition_snapshot = (
                SELECT test_case.precondition
                FROM test_case
                WHERE test_case.id = test_execution.test_case_id
            ),
            steps_snapshot = COALESCE(
                (SELECT NULLIF(TRIM(test_case.steps), '')
                 FROM test_case
                 WHERE test_case.id = test_execution.test_case_id),
                'Sample legacy test steps were not available.'
            ),
            expected_result_snapshot = COALESCE(
                (SELECT NULLIF(TRIM(test_case.expected_result), '')
                 FROM test_case
                 WHERE test_case.id = test_execution.test_case_id),
                'Sample legacy expected result was not available.'
            )
        """
    )

    with op.batch_alter_table('test_execution', schema=None) as batch_op:
        batch_op.alter_column(
            'test_case_code_snapshot',
            existing_type=sa.String(length=80),
            nullable=False,
        )
        batch_op.alter_column(
            'test_case_title_snapshot',
            existing_type=sa.String(length=200),
            nullable=False,
        )
        batch_op.alter_column(
            'steps_snapshot',
            existing_type=sa.Text(),
            nullable=False,
        )
        batch_op.alter_column(
            'expected_result_snapshot',
            existing_type=sa.Text(),
            nullable=False,
        )
        batch_op.create_index(
            batch_op.f('ix_test_execution_executed_at'),
            ['executed_at'],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_test_execution_result'),
            ['result'],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_test_execution_test_case_id'),
            ['test_case_id'],
            unique=False,
        )
        batch_op.drop_column('version_id')

    with op.batch_alter_table('test_case', schema=None) as batch_op:
        batch_op.alter_column('steps',
               existing_type=sa.TEXT(),
               nullable=False)
        batch_op.alter_column('expected_result',
               existing_type=sa.TEXT(),
               nullable=False)
        batch_op.create_index(batch_op.f('ix_test_case_status'), ['status'], unique=False)
        batch_op.drop_column('project_id')
        batch_op.drop_column('is_active')

    set_sqlite_foreign_keys(True)
    check_sqlite_foreign_keys()


def downgrade():
    set_sqlite_foreign_keys(False)

    with op.batch_alter_table('test_case', schema=None) as batch_op:
        batch_op.add_column(sa.Column('project_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=True))

    op.execute(
        """
        UPDATE test_case
        SET project_id = (
                SELECT version.project_id
                FROM version
                WHERE version.id = test_case.version_id
            ),
            is_active = CASE WHEN status = 'archived' THEN 0 ELSE 1 END
        """
    )

    with op.batch_alter_table('test_case', schema=None) as batch_op:
        batch_op.alter_column(
            'project_id', existing_type=sa.Integer(), nullable=False
        )
        batch_op.alter_column(
            'is_active', existing_type=sa.Boolean(), nullable=False
        )
        batch_op.create_foreign_key(
            'fk_test_case_project_id_project',
            'project',
            ['project_id'],
            ['id'],
        )
        batch_op.drop_index(batch_op.f('ix_test_case_status'))
        batch_op.alter_column(
            'expected_result', existing_type=sa.Text(), nullable=True
        )
        batch_op.alter_column('steps', existing_type=sa.Text(), nullable=True)

    with op.batch_alter_table('test_execution', schema=None) as batch_op:
        batch_op.add_column(sa.Column('version_id', sa.Integer(), nullable=True))

    op.execute(
        """
        UPDATE test_execution
        SET version_id = (
            SELECT test_case.version_id
            FROM test_case
            WHERE test_case.id = test_execution.test_case_id
        )
        """
    )

    with op.batch_alter_table('test_execution', schema=None) as batch_op:
        batch_op.alter_column(
            'version_id', existing_type=sa.Integer(), nullable=False
        )
        batch_op.create_foreign_key(
            'fk_test_execution_version_id_version',
            'version',
            ['version_id'],
            ['id'],
        )
        batch_op.drop_index(batch_op.f('ix_test_execution_test_case_id'))
        batch_op.drop_index(batch_op.f('ix_test_execution_result'))
        batch_op.drop_index(batch_op.f('ix_test_execution_executed_at'))
        batch_op.drop_column('expected_result_snapshot')
        batch_op.drop_column('steps_snapshot')
        batch_op.drop_column('precondition_snapshot')
        batch_op.drop_column('test_case_title_snapshot')
        batch_op.drop_column('test_case_code_snapshot')

    set_sqlite_foreign_keys(True)
    check_sqlite_foreign_keys()
