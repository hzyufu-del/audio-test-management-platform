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

    versions = db.relationship("Version", back_populates="project", lazy=True)
    testcases = db.relationship("TestCase", back_populates="project", lazy=True)
    defects = db.relationship("Defect", back_populates="project", lazy=True)
    log_files = db.relationship("LogFile", back_populates="project", lazy=True)

    def __repr__(self):
        return f"<Project {self.code}>"


class Version(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    release_type = db.Column(db.String(40), default="sample", nullable=False)
    status = db.Column(db.String(30), default="planning", nullable=False)
    planned_test_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    project = db.relationship("Project", back_populates="versions")
    executions = db.relationship("TestExecution", back_populates="version", lazy=True)
    defects = db.relationship("Defect", back_populates="version", lazy=True)
    log_files = db.relationship("LogFile", back_populates="version", lazy=True)

    def __repr__(self):
        return f"<Version {self.name}>"


class TestCase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    module = db.Column(db.String(80), nullable=False)
    priority = db.Column(db.String(20), default="P2", nullable=False)
    case_type = db.Column(db.String(40), default="checklist", nullable=False)
    precondition = db.Column(db.Text)
    steps = db.Column(db.Text)
    expected_result = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    project = db.relationship("Project", back_populates="testcases")
    executions = db.relationship("TestExecution", back_populates="testcase", lazy=True)

    def __repr__(self):
        return f"<TestCase {self.title}>"


class TestExecution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    testcase_id = db.Column(db.Integer, db.ForeignKey("test_case.id"), nullable=False)
    version_id = db.Column(db.Integer, db.ForeignKey("version.id"), nullable=False)
    executor_name = db.Column(db.String(80), nullable=False)
    result = db.Column(db.String(30), default="not_run", nullable=False)
    executed_at = db.Column(db.DateTime(timezone=True))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    testcase = db.relationship("TestCase", back_populates="executions")
    version = db.relationship("Version", back_populates="executions")

    def __repr__(self):
        return f"<TestExecution {self.result}>"


class Defect(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    version_id = db.Column(db.Integer, db.ForeignKey("version.id"))
    title = db.Column(db.String(200), nullable=False)
    severity = db.Column(db.String(20), default="medium", nullable=False)
    status = db.Column(db.String(30), default="open", nullable=False)
    reported_by = db.Column(db.String(80))
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    project = db.relationship("Project", back_populates="defects")
    version = db.relationship("Version", back_populates="defects")

    def __repr__(self):
        return f"<Defect {self.title}>"


class LogFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    version_id = db.Column(db.Integer, db.ForeignKey("version.id"))
    filename = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(60), default="sample", nullable=False)
    storage_path = db.Column(db.String(255))
    uploaded_by = db.Column(db.String(80))
    notes = db.Column(db.Text)
    uploaded_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    project = db.relationship("Project", back_populates="log_files")
    version = db.relationship("Version", back_populates="log_files")

    def __repr__(self):
        return f"<LogFile {self.filename}>"
