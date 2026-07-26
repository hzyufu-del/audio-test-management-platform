from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email}>"


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(40), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    status = db.Column(db.String(30), default="active", nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    versions = db.relationship("Version", back_populates="project", lazy=True)
    log_files = db.relationship("LogFile", back_populates="project", lazy=True)
    test_design_sessions = db.relationship(
        "TestDesignSession",
        back_populates="project",
        lazy=True,
    )

    def __repr__(self):
        return f"<Project {self.code}>"


class Version(db.Model):
    __table_args__ = (
        db.UniqueConstraint("project_id", "code", name="uq_version_project_code"),
    )

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text)
    release_type = db.Column(db.String(40), default="sample", nullable=False)
    status = db.Column(db.String(30), default="planned", nullable=False)
    planned_test_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    project = db.relationship("Project", back_populates="versions")
    testcases = db.relationship("TestCase", back_populates="version", lazy=True)
    test_runs = db.relationship("TestRun", back_populates="version", lazy=True)
    log_files = db.relationship("LogFile", back_populates="version", lazy=True)
    test_design_sessions = db.relationship(
        "TestDesignSession",
        back_populates="version",
        lazy=True,
    )

    def __repr__(self):
        return f"<Version {self.name}>"


class TestRun(db.Model):
    __table_args__ = (
        db.UniqueConstraint(
            "version_id",
            "source_type",
            "report_hash",
            name="uq_test_run_version_source_hash",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(
        db.Integer,
        db.ForeignKey("version.id"),
        nullable=False,
        index=True,
    )
    source_type = db.Column(
        db.String(30),
        default="junit_xml",
        nullable=False,
    )
    report_hash = db.Column(db.String(64), nullable=False)
    runner = db.Column(db.String(80))
    environment = db.Column(db.String(120))
    started_at = db.Column(db.DateTime(timezone=True))
    finished_at = db.Column(db.DateTime(timezone=True))
    imported_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    version = db.relationship("Version", back_populates="test_runs")
    executions = db.relationship("TestExecution", back_populates="test_run", lazy=True)

    def __repr__(self):
        return f"<TestRun {self.source_type}:{self.report_hash[:12]}>"


class TestCase(db.Model):
    __table_args__ = (
        db.UniqueConstraint("version_id", "code", name="uq_test_case_version_code"),
    )

    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(db.Integer, db.ForeignKey("version.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(80), nullable=False)
    module = db.Column(db.String(80), nullable=False)
    priority = db.Column(db.String(20), default="P2", nullable=False)
    case_type = db.Column(db.String(40), default="checklist", nullable=False)
    precondition = db.Column(db.Text)
    steps = db.Column(db.Text, nullable=False)
    expected_result = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), default="draft", nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    version = db.relationship("Version", back_populates="testcases")
    executions = db.relationship("TestExecution", back_populates="testcase", lazy=True)
    accepted_draft = db.relationship(
        "TestCaseDraft",
        back_populates="accepted_test_case",
        foreign_keys="TestCaseDraft.accepted_test_case_id",
        uselist=False,
    )

    def __repr__(self):
        return f"<TestCase {self.title}>"


class TestDesignSession(db.Model):
    __table_args__ = (
        db.CheckConstraint(
            "status IN "
            "('generated', 'partially_reviewed', 'accepted', 'rejected')",
            name="ck_test_design_session_status",
        ),
        db.CheckConstraint(
            "provider IN ('mock', 'deepseek')",
            name="ck_test_design_session_provider",
        ),
        db.CheckConstraint(
            "quality_score >= 0 AND quality_score <= 100",
            name="ck_test_design_session_quality_score",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("project.id"),
        nullable=False,
        index=True,
    )
    version_id = db.Column(
        db.Integer,
        db.ForeignKey("version.id"),
        nullable=False,
        index=True,
    )
    title = db.Column(db.String(200), nullable=False)
    requirement_text = db.Column(db.Text, nullable=False)
    status = db.Column(
        db.String(30),
        default="generated",
        nullable=False,
        index=True,
    )
    provider = db.Column(db.String(30), nullable=False, index=True)
    provider_model = db.Column(db.String(120))
    prompt_version = db.Column(db.String(40), nullable=False)
    quality_score = db.Column(db.Integer, nullable=False)
    test_points_json = db.Column(db.Text, nullable=False)
    limitations_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    project = db.relationship("Project", back_populates="test_design_sessions")
    version = db.relationship("Version", back_populates="test_design_sessions")
    drafts = db.relationship(
        "TestCaseDraft",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy=True,
    )

    def __repr__(self):
        return f"<TestDesignSession {self.title}>"


class TestCaseDraft(db.Model):
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')",
            name="ck_test_case_draft_status",
        ),
        db.CheckConstraint(
            "scenario_type IN "
            "('normal', 'negative', 'boundary', 'compatibility', "
            "'recovery', 'security')",
            name="ck_test_case_draft_scenario_type",
        ),
        db.CheckConstraint(
            "("
            "status = 'accepted' AND accepted_test_case_id IS NOT NULL"
            ") OR ("
            "status != 'accepted' AND accepted_test_case_id IS NULL"
            ")",
            name="ck_test_case_draft_accepted_link",
        ),
        db.UniqueConstraint(
            "accepted_test_case_id",
            name="uq_test_case_draft_accepted_case",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("test_design_session.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    suggested_code = db.Column(db.String(80), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    module = db.Column(db.String(80), nullable=False)
    priority = db.Column(db.String(20), nullable=False)
    case_type = db.Column(db.String(40), nullable=False)
    precondition = db.Column(db.Text)
    steps = db.Column(db.Text, nullable=False)
    expected_result = db.Column(db.Text, nullable=False)
    scenario_type = db.Column(db.String(30), nullable=False)
    status = db.Column(
        db.String(30),
        default="pending",
        nullable=False,
        index=True,
    )
    accepted_test_case_id = db.Column(
        db.Integer,
        db.ForeignKey("test_case.id"),
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    session = db.relationship("TestDesignSession", back_populates="drafts")
    accepted_test_case = db.relationship(
        "TestCase",
        back_populates="accepted_draft",
        foreign_keys=[accepted_test_case_id],
    )

    def __repr__(self):
        return f"<TestCaseDraft {self.suggested_code}:{self.status}>"


class TestExecution(db.Model):
    __table_args__ = (
        db.UniqueConstraint(
            "test_run_id",
            "external_case_key",
            name="uq_test_execution_run_external_key",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    test_run_id = db.Column(
        db.Integer,
        db.ForeignKey("test_run.id"),
        nullable=True,
        index=True,
    )
    test_case_id = db.Column(
        db.Integer,
        db.ForeignKey("test_case.id"),
        nullable=False,
        index=True,
    )
    external_case_key = db.Column(db.String(255))
    duration_seconds = db.Column(db.Numeric(10, 3))
    result = db.Column(db.String(30), default="passed", nullable=False, index=True)
    actual_result = db.Column(db.Text)
    tester = db.Column(db.String(80), nullable=False)
    environment = db.Column(db.String(120))
    executed_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )
    notes = db.Column(db.Text)
    test_case_code_snapshot = db.Column(db.String(80), nullable=False)
    test_case_title_snapshot = db.Column(db.String(200), nullable=False)
    precondition_snapshot = db.Column(db.Text)
    steps_snapshot = db.Column(db.Text, nullable=False)
    expected_result_snapshot = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    testcase = db.relationship("TestCase", back_populates="executions")
    test_run = db.relationship("TestRun", back_populates="executions")
    defects = db.relationship("Defect", back_populates="execution", lazy=True)

    def capture_test_case_snapshot(self, test_case):
        self.testcase = test_case
        self.test_case_code_snapshot = test_case.code
        self.test_case_title_snapshot = test_case.title
        self.precondition_snapshot = test_case.precondition
        self.steps_snapshot = test_case.steps
        self.expected_result_snapshot = test_case.expected_result

    def __repr__(self):
        return f"<TestExecution {self.result}>"


class Defect(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_execution_id = db.Column(
        db.Integer,
        db.ForeignKey("test_execution.id"),
        nullable=False,
        index=True,
    )
    code = db.Column(db.String(40), unique=True, nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    component = db.Column(db.String(80), nullable=False)
    severity = db.Column(db.String(20), default="major", nullable=False)
    priority = db.Column(db.String(20), default="P2", nullable=False)
    status = db.Column(db.String(30), default="open", nullable=False)
    reproduction_steps = db.Column(db.Text, nullable=False)
    observed_result = db.Column(db.Text, nullable=False)
    reporter = db.Column(db.String(80), nullable=False)
    assignee = db.Column(db.String(80))
    resolution = db.Column(db.String(80))
    resolution_note = db.Column(db.Text)
    environment_snapshot = db.Column(db.String(120))
    actual_result_snapshot = db.Column(db.Text)
    executed_at_snapshot = db.Column(db.DateTime(timezone=True), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    execution = db.relationship("TestExecution", back_populates="defects")

    def capture_execution_snapshot(self, execution):
        self.execution = execution
        self.environment_snapshot = execution.environment
        self.actual_result_snapshot = execution.actual_result
        self.executed_at_snapshot = execution.executed_at

    def __repr__(self):
        return f"<Defect {self.code}>"


class LogFile(db.Model):
    __table_args__ = (
        db.UniqueConstraint(
            "project_id",
            "sha256",
            name="uq_log_file_project_sha256",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    version_id = db.Column(db.Integer, db.ForeignKey("version.id"))
    filename = db.Column(db.String(200), nullable=False)
    file_size_bytes = db.Column(db.Integer, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    analysis_status = db.Column(
        db.String(30),
        default="completed",
        nullable=False,
    )
    risk_level = db.Column(db.String(20), nullable=False)
    total_lines = db.Column(db.Integer, nullable=False)
    critical_count = db.Column(db.Integer, default=0, nullable=False)
    error_count = db.Column(db.Integer, default=0, nullable=False)
    warning_count = db.Column(db.Integer, default=0, nullable=False)
    info_count = db.Column(db.Integer, default=0, nullable=False)
    analysis_summary = db.Column(db.Text, nullable=False)
    uploaded_by = db.Column(db.String(80), nullable=False)
    notes = db.Column(db.Text)
    uploaded_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    project = db.relationship("Project", back_populates="log_files")
    version = db.relationship("Version", back_populates="log_files")

    def __repr__(self):
        return f"<LogFile {self.filename}>"
