from datetime import timedelta
from pathlib import Path

import click
from flask import Flask
from sqlalchemy import inspect

from config import Config

from .extensions import db, login_manager, migrate


def create_app(config_overrides=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    if config_overrides:
        app.config.update(config_overrides)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "请先登录后再访问该页面。"

    register_blueprints(app)
    register_cli_commands(app)
    register_login_loader()

    return app


def register_blueprints(app):
    from .blueprints.auth import bp as auth_bp
    from .blueprints.dashboard import bp as dashboard_bp
    from .blueprints.defects import bp as defects_bp
    from .blueprints.executions import bp as executions_bp
    from .blueprints.logs import bp as logs_bp
    from .blueprints.projects import bp as projects_bp
    from .blueprints.testcases import bp as testcases_bp
    from .blueprints.test_runs import bp as test_runs_bp
    from .blueprints.versions import bp as versions_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(versions_bp)
    app.register_blueprint(testcases_bp)
    app.register_blueprint(executions_bp)
    app.register_blueprint(test_runs_bp)
    app.register_blueprint(defects_bp)
    app.register_blueprint(logs_bp)


def register_cli_commands(app):
    @app.cli.command("init-db")
    def init_db():
        """Seed local mock/demo/sample data after migrations are applied."""
        with app.app_context():
            ensure_migrated_database()
            seed_demo_data()
        click.echo("Seeded mock/demo/sample data.")


def ensure_migrated_database():
    from .models import (
        Defect,
        LogFile,
        Project,
        TestCase,
        TestExecution,
        TestRun,
        User,
        Version,
    )

    required_tables = {
        model.__tablename__
        for model in (
            User,
            Project,
            Version,
            TestCase,
            TestRun,
            TestExecution,
            Defect,
            LogFile,
        )
    }
    existing_tables = set(inspect(db.engine).get_table_names())
    missing_tables = required_tables - existing_tables

    if missing_tables:
        raise click.ClickException(
            "Database tables are missing. Run 'flask --app run.py db upgrade' "
            "before 'flask --app run.py init-db'."
        )


def seed_demo_data():
    from .models import (
        Defect,
        LogFile,
        Project,
        TestCase,
        TestExecution,
        User,
        Version,
        utc_now,
    )

    seeded_at = utc_now()

    def ensure_project(code, name, description, status="active"):
        item = Project.query.filter_by(code=code).first()
        if item is None:
            item = Project(code=code)
            db.session.add(item)
        item.name = name
        item.description = description
        item.status = status
        db.session.flush()
        return item

    def ensure_version(project, code, name, status):
        item = Version.query.filter_by(project_id=project.id, code=code).first()
        if item is None:
            item = Version(project_id=project.id, code=code)
            db.session.add(item)
        item.name = name
        item.description = "Sample version record for local demo use."
        item.release_type = "sample"
        item.status = status
        db.session.flush()
        return item

    def ensure_testcase(version, code, title, module, priority="P2", status="active"):
        item = TestCase.query.filter_by(version_id=version.id, code=code).first()
        if item is None:
            item = TestCase(version_id=version.id, code=code)
            db.session.add(item)
        item.title = title
        item.module = module
        item.priority = priority
        item.case_type = "checklist"
        item.precondition = "Use mock device state only."
        item.steps = f"Run sample {module.lower()} checklist steps."
        item.expected_result = f"Sample {module.lower()} result is recorded."
        item.status = status
        db.session.flush()
        return item

    def ensure_execution(
        testcase,
        marker,
        result,
        days_ago,
        tester="Demo Tester",
        environment="Android Demo Env",
        legacy_tester=None,
    ):
        item = TestExecution.query.filter_by(notes=marker).first()
        if item is None and legacy_tester:
            item = TestExecution.query.filter_by(
                test_case_id=testcase.id,
                tester=legacy_tester,
            ).first()
        if item is None:
            item = TestExecution()
            db.session.add(item)
        item.result = result
        item.actual_result = (
            "Demo failed audio output is recorded." if result == "failed" else ""
        )
        item.tester = tester
        item.environment = environment
        item.executed_at = seeded_at - timedelta(days=days_ago)
        item.notes = marker
        item.capture_test_case_snapshot(testcase)
        db.session.flush()
        return item

    def ensure_defect(execution, code, title, status, severity, priority):
        item = Defect.query.filter_by(code=code).first()
        if item is None:
            item = Defect(code=code)
            db.session.add(item)
        item.title = title
        item.description = "Sample issue observed during a failed demo execution."
        item.component = "Audio"
        item.severity = severity
        item.priority = priority
        item.status = status
        item.reproduction_steps = "Run sample reproduction steps using mock data."
        item.observed_result = "Sample unexpected output is recorded."
        item.reporter = "Demo Reporter"
        item.assignee = "Sample Assignee" if status == "fixed" else None
        item.resolution = "sample_fix" if status in {"fixed", "closed"} else None
        item.resolution_note = "Sample resolution note." if item.resolution else None
        item.capture_execution_snapshot(execution)
        db.session.flush()
        return item

    demo_user = User.query.filter_by(email="demo@example.com").first()
    if demo_user is None:
        demo_user = User(username="demo_tester", email="demo@example.com")
        demo_user.set_password("demo-password")
        db.session.add(demo_user)

    project = ensure_project(
        "MOCK-AUDIO-01",
        "Demo Audio Device A",
        "Mock project for consumer audio testing workflows.",
    )
    second_project = ensure_project(
        "MOCK-AUDIO-02",
        "Sample Audio Device B",
        "Sample project for cross-project quality comparison.",
    )

    version = ensure_version(project, "FW_DEMO_ALPHA", "Demo Firmware Alpha", "testing")
    ensure_version(project, "FW_DEMO_BETA", "Demo Firmware Beta", "planned")
    second_version = ensure_version(
        second_project,
        "FW_SAMPLE_GAMMA",
        "Sample Firmware Gamma",
        "testing",
    )

    testcase = ensure_testcase(
        version,
        "TC_AUDIO_001",
        "Sample Audio Playback Checklist",
        "Audio",
        priority="P1",
    )
    bluetooth_testcase = ensure_testcase(
        version,
        "TC_BT_001",
        "Sample Bluetooth Reconnect Checklist",
        "Bluetooth",
    )
    charging_testcase = ensure_testcase(
        second_version,
        "TC_CHARGING_001",
        "Sample Charging Status Checklist",
        "Charging",
    )
    bluetooth_testcase.precondition = ""
    charging_testcase.expected_result = "显示正常"

    failed_execution = ensure_execution(
        testcase,
        "seed:dashboard:audio-failed",
        "failed",
        1,
        legacy_tester="Demo Tester",
    )
    ensure_execution(
        testcase,
        "seed:dashboard:audio-passed",
        "passed",
        2,
        tester="Sample Tester A",
    )
    ensure_execution(
        testcase,
        "seed:dashboard:audio-blocked",
        "blocked",
        3,
        tester="Sample Tester B",
        environment="Firmware Demo Env",
    )
    ensure_execution(
        testcase,
        "seed:dashboard:audio-skipped",
        "skipped",
        5,
        tester="Sample Tester A",
    )
    ensure_execution(
        bluetooth_testcase,
        "seed:dashboard:bluetooth-failed-no-defect",
        "failed",
        8,
        tester="Demo Tester",
    )
    ensure_execution(
        bluetooth_testcase,
        "seed:dashboard:bluetooth-passed",
        "passed",
        18,
        tester="Sample Tester B",
    )
    second_failed = ensure_execution(
        charging_testcase,
        "seed:dashboard:charging-failed",
        "failed",
        4,
        tester="Sample Tester C",
        environment="iOS Demo Env",
    )
    ensure_execution(
        charging_testcase,
        "seed:dashboard:charging-passed",
        "passed",
        12,
        tester="Sample Tester C",
        environment="iOS Demo Env",
    )

    ensure_defect(
        failed_execution,
        "DEF_DEMO_001",
        "Sample Audio Interruption Defect",
        "open",
        "blocker",
        "P0",
    )
    ensure_defect(
        failed_execution,
        "DEF_DEMO_002",
        "Demo Audio State Recovery Defect",
        "fixed",
        "critical",
        "P1",
    )
    ensure_defect(
        second_failed,
        "DEF_DEMO_003",
        "Sample Charging Indicator Defect",
        "closed",
        "major",
        "P2",
    )
    ensure_defect(
        second_failed,
        "DEF_DEMO_004",
        "Demo Charging Display Observation",
        "rejected",
        "minor",
        "P3",
    )

    from .services.log_analysis_service import LogTextParser

    demo_log_content = (
        b"2026-07-26 INFO mock audio connection established\n"
        b"2026-07-26 WARNING demo battery voltage is low\n"
        b"2026-07-26 ERROR sample audio protocol timeout"
    )
    log_analysis = LogTextParser().analyze(
        "sample_audio_check.log",
        demo_log_content,
    )
    log_file = LogFile.query.filter_by(
        project_id=project.id,
        sha256=log_analysis.sha256,
    ).first()
    if log_file is None:
        log_file = LogFile.query.filter_by(
            project_id=project.id,
            filename=log_analysis.filename,
        ).first()
    if log_file is None:
        log_file = LogFile(project_id=project.id)
        db.session.add(log_file)

    log_file.version_id = version.id
    log_file.filename = log_analysis.filename
    log_file.file_size_bytes = log_analysis.file_size_bytes
    log_file.sha256 = log_analysis.sha256
    log_file.analysis_status = "completed"
    log_file.risk_level = log_analysis.risk_level
    log_file.total_lines = log_analysis.total_lines
    log_file.critical_count = log_analysis.level_counts["critical"]
    log_file.error_count = log_analysis.level_counts["error"]
    log_file.warning_count = log_analysis.level_counts["warning"]
    log_file.info_count = log_analysis.level_counts["info"]
    log_file.analysis_summary = log_analysis.summary_json
    log_file.uploaded_by = "demo_tester"
    log_file.notes = (
        "Mock/demo/sample analysis metadata only; original log content "
        "is not stored."
    )

    db.session.commit()


def register_login_loader():
    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        if not user_id.isdigit():
            return None
        return db.session.get(User, int(user_id))
