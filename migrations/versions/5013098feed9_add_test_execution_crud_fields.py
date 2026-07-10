"""add test execution crud fields

Revision ID: 5013098feed9
Revises: 8ca595558401
Create Date: 2026-07-10 00:06:25.762363

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5013098feed9'
down_revision = '8ca595558401'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('test_execution', schema=None) as batch_op:
        batch_op.add_column(sa.Column('test_case_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('actual_result', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('tester', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('environment', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))

    op.execute("UPDATE test_execution SET test_case_id = testcase_id WHERE test_case_id IS NULL")
    op.execute("UPDATE test_execution SET tester = executor_name WHERE tester IS NULL OR tester = ''")
    op.execute("UPDATE test_execution SET tester = 'Demo Tester' WHERE tester IS NULL OR tester = ''")
    op.execute("UPDATE test_execution SET result = 'passed' WHERE result IN ('pass', 'Pass', 'PASS')")
    op.execute("UPDATE test_execution SET result = 'failed' WHERE result IN ('fail', 'Fail', 'FAIL')")
    op.execute("UPDATE test_execution SET result = 'blocked' WHERE result IN ('block', 'Blocked', 'BLOCKED')")
    op.execute("UPDATE test_execution SET result = 'skipped' WHERE result IN ('not_run', 'Not Run', 'NOT_RUN')")
    op.execute("UPDATE test_execution SET result = 'passed' WHERE result NOT IN ('passed', 'failed', 'blocked', 'skipped')")
    op.execute("UPDATE test_execution SET actual_result = 'Demo actual result is recorded.' WHERE actual_result IS NULL")
    op.execute("UPDATE test_execution SET executed_at = CURRENT_TIMESTAMP WHERE executed_at IS NULL")
    op.execute("UPDATE test_execution SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")

    with op.batch_alter_table('test_execution', schema=None) as batch_op:
        batch_op.alter_column('test_case_id', existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column('tester', existing_type=sa.String(length=80), nullable=False)
        batch_op.alter_column('updated_at', existing_type=sa.DateTime(timezone=True), nullable=False)
        batch_op.alter_column('executed_at',
               existing_type=sa.DATETIME(),
               nullable=False)
        batch_op.create_foreign_key('fk_test_execution_test_case_id_test_case', 'test_case', ['test_case_id'], ['id'])
        batch_op.drop_column('testcase_id')
        batch_op.drop_column('executor_name')


def downgrade():
    with op.batch_alter_table('test_execution', schema=None) as batch_op:
        batch_op.add_column(sa.Column('executor_name', sa.VARCHAR(length=80), nullable=True))
        batch_op.add_column(sa.Column('testcase_id', sa.INTEGER(), nullable=True))

    op.execute("UPDATE test_execution SET testcase_id = test_case_id WHERE testcase_id IS NULL")
    op.execute("UPDATE test_execution SET executor_name = tester WHERE executor_name IS NULL OR executor_name = ''")
    op.execute("UPDATE test_execution SET result = 'pass' WHERE result = 'passed'")
    op.execute("UPDATE test_execution SET result = 'fail' WHERE result = 'failed'")

    with op.batch_alter_table('test_execution', schema=None) as batch_op:
        batch_op.alter_column('executor_name', existing_type=sa.String(length=80), nullable=False)
        batch_op.alter_column('testcase_id', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_constraint('fk_test_execution_test_case_id_test_case', type_='foreignkey')
        batch_op.create_foreign_key('fk_test_execution_testcase_id_test_case', 'test_case', ['testcase_id'], ['id'])
        batch_op.alter_column('executed_at',
               existing_type=sa.DATETIME(),
               nullable=True)
        batch_op.drop_column('updated_at')
        batch_op.drop_column('environment')
        batch_op.drop_column('tester')
        batch_op.drop_column('actual_result')
        batch_op.drop_column('test_case_id')
