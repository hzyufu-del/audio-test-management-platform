"""add defect management v1

Revision ID: 9122e14c70bb
Revises: fea6fb74549f
Create Date: 2026-07-11 16:30:41.238362

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9122e14c70bb'
down_revision = 'fea6fb74549f'
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

    op.execute(
        """
        UPDATE defect
        SET description = 'Sample migrated defect description.'
        WHERE description IS NULL OR TRIM(description) = ''
        """
    )

    with op.batch_alter_table('defect', schema=None) as batch_op:
        batch_op.add_column(sa.Column('test_execution_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('code', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('component', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('priority', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('reproduction_steps', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('observed_result', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('reporter', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('assignee', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('resolution', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('resolution_note', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('environment_snapshot', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('actual_result_snapshot', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('executed_at_snapshot', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))

    op.execute(
        """
        UPDATE defect
        SET test_execution_id = (
            SELECT MIN(test_execution.id)
            FROM test_execution
            JOIN test_case ON test_case.id = test_execution.test_case_id
            JOIN version ON version.id = test_case.version_id
            WHERE (defect.version_id IS NOT NULL
                   AND test_case.version_id = defect.version_id)
               OR (defect.version_id IS NULL
                   AND version.project_id = defect.project_id)
        )
        """
    )

    unresolved_count = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM defect WHERE test_execution_id IS NULL")
    ).scalar_one()
    if unresolved_count:
        raise RuntimeError(
            f'{unresolved_count} existing defect record(s) have no TestExecution'
        )

    if op.get_bind().dialect.name == 'sqlite':
        op.execute("UPDATE defect SET code = printf('DEF_DEMO_%03d', id)")
    else:
        op.execute("UPDATE defect SET code = CONCAT('DEF_DEMO_', id)")

    op.execute(
        """
        UPDATE defect
        SET component = 'Audio',
            priority = 'P2',
            reproduction_steps = 'Run sample reproduction steps for migrated demo defect.',
            observed_result = description,
            reporter = COALESCE(NULLIF(TRIM(reported_by), ''), 'Demo Reporter'),
            environment_snapshot = (
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
            updated_at = CURRENT_TIMESTAMP,
            severity = CASE
                WHEN LOWER(severity) IN ('blocker', 'critical', 'major', 'minor')
                    THEN LOWER(severity)
                WHEN LOWER(severity) = 'high' THEN 'critical'
                WHEN LOWER(severity) = 'low' THEN 'minor'
                ELSE 'major'
            END,
            status = CASE
                WHEN LOWER(status) IN ('open', 'fixed', 'closed', 'rejected')
                    THEN LOWER(status)
                ELSE 'open'
            END
        """
    )

    with op.batch_alter_table('defect', schema=None) as batch_op:
        batch_op.alter_column(
            'test_execution_id', existing_type=sa.Integer(), nullable=False
        )
        batch_op.alter_column(
            'code', existing_type=sa.String(length=40), nullable=False
        )
        batch_op.alter_column(
            'component', existing_type=sa.String(length=80), nullable=False
        )
        batch_op.alter_column(
            'priority', existing_type=sa.String(length=20), nullable=False
        )
        batch_op.alter_column(
            'reproduction_steps', existing_type=sa.Text(), nullable=False
        )
        batch_op.alter_column(
            'observed_result', existing_type=sa.Text(), nullable=False
        )
        batch_op.alter_column(
            'reporter', existing_type=sa.String(length=80), nullable=False
        )
        batch_op.alter_column(
            'executed_at_snapshot',
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )
        batch_op.alter_column(
            'updated_at', existing_type=sa.DateTime(timezone=True), nullable=False
        )
        batch_op.alter_column('description',
               existing_type=sa.TEXT(),
               nullable=False)
        batch_op.create_index(batch_op.f('ix_defect_code'), ['code'], unique=True)
        batch_op.create_index(batch_op.f('ix_defect_test_execution_id'), ['test_execution_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_defect_test_execution_id_test_execution',
            'test_execution',
            ['test_execution_id'],
            ['id'],
        )
        batch_op.drop_column('project_id')
        batch_op.drop_column('reported_by')
        batch_op.drop_column('version_id')

    set_sqlite_foreign_keys(True)
    check_sqlite_foreign_keys()


def downgrade():
    set_sqlite_foreign_keys(False)

    with op.batch_alter_table('defect', schema=None) as batch_op:
        batch_op.add_column(sa.Column('version_id', sa.INTEGER(), nullable=True))
        batch_op.add_column(sa.Column('reported_by', sa.VARCHAR(length=80), nullable=True))
        batch_op.add_column(sa.Column('project_id', sa.INTEGER(), nullable=True))

    op.execute(
        """
        UPDATE defect
        SET version_id = (
                SELECT test_case.version_id
                FROM test_execution
                JOIN test_case ON test_case.id = test_execution.test_case_id
                WHERE test_execution.id = defect.test_execution_id
            ),
            project_id = (
                SELECT version.project_id
                FROM test_execution
                JOIN test_case ON test_case.id = test_execution.test_case_id
                JOIN version ON version.id = test_case.version_id
                WHERE test_execution.id = defect.test_execution_id
            ),
            reported_by = reporter,
            severity = CASE
                WHEN severity IN ('blocker', 'critical') THEN 'high'
                WHEN severity = 'minor' THEN 'low'
                ELSE 'medium'
            END
        """
    )

    with op.batch_alter_table('defect', schema=None) as batch_op:
        batch_op.alter_column(
            'project_id', existing_type=sa.Integer(), nullable=False
        )
        batch_op.drop_constraint(
            'fk_defect_test_execution_id_test_execution', type_='foreignkey'
        )
        batch_op.create_foreign_key(
            'fk_defect_project_id_project', 'project', ['project_id'], ['id']
        )
        batch_op.create_foreign_key(
            'fk_defect_version_id_version', 'version', ['version_id'], ['id']
        )
        batch_op.drop_index(batch_op.f('ix_defect_test_execution_id'))
        batch_op.drop_index(batch_op.f('ix_defect_code'))
        batch_op.alter_column('description',
               existing_type=sa.TEXT(),
               nullable=True)
        batch_op.drop_column('updated_at')
        batch_op.drop_column('executed_at_snapshot')
        batch_op.drop_column('actual_result_snapshot')
        batch_op.drop_column('environment_snapshot')
        batch_op.drop_column('resolution_note')
        batch_op.drop_column('resolution')
        batch_op.drop_column('assignee')
        batch_op.drop_column('reporter')
        batch_op.drop_column('observed_result')
        batch_op.drop_column('reproduction_steps')
        batch_op.drop_column('priority')
        batch_op.drop_column('component')
        batch_op.drop_column('code')
        batch_op.drop_column('test_execution_id')

    set_sqlite_foreign_keys(True)
    check_sqlite_foreign_keys()
