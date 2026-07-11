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
    from .blueprints.versions import bp as versions_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(versions_bp)
    app.register_blueprint(testcases_bp)
    app.register_blueprint(executions_bp)
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
    from .models import Defect, LogFile, Project, TestCase, TestExecution, User, Version

    required_tables = {
        model.__tablename__
        for model in (User, Project, Version, TestCase, TestExecution, Defect, LogFile)
    }
    existing_tables = set(inspect(db.engine).get_table_names())
    missing_tables = required_tables - existing_tables

    if missing_tables:
        raise click.ClickException(
            "Database tables are missing. Run 'flask --app run.py db upgrade' "
            "before 'flask --app run.py init-db'."
        )


def seed_demo_data():
    from .models import Defect, LogFile, Project, TestCase, TestExecution, User, Version

    demo_user = User.query.filter_by(email="demo@example.com").first()
    if demo_user is None:
        demo_user = User(username="demo_tester", email="demo@example.com")
        demo_user.set_password("demo-password")
        db.session.add(demo_user)

    project = Project.query.filter_by(code="MOCK-AUDIO-01").first()
    if project is None:
        project = Project(
            name="Demo Audio Earbuds",
            code="MOCK-AUDIO-01",
            description="Mock project for consumer audio testing workflows.",
            status="active",
        )
        db.session.add(project)
        db.session.flush()

    version = Version.query.filter_by(project_id=project.id, code="FW_DEMO_ALPHA").first()
    if version is None:
        version = Version(
            project_id=project.id,
            name="Demo Firmware Alpha",
            code="FW_DEMO_ALPHA",
            description="Sample version record for local demo use.",
            release_type="sample",
            status="testing",
        )
        db.session.add(version)
        db.session.flush()

    testcase = TestCase.query.filter_by(
        version_id=version.id,
        code="TC_AUDIO_001",
    ).first()
    if testcase is None:
        testcase = TestCase(
            version_id=version.id,
            title="Sample Audio Playback Checklist",
            code="TC_AUDIO_001",
            module="Audio",
            priority="P1",
            case_type="checklist",
            precondition="Use mock audio device state only.",
            steps="Open sample audio playback flow and check basic output.",
            expected_result="Playback status is recorded as a demo result.",
            status="active",
        )
        db.session.add(testcase)
        db.session.flush()

    bluetooth_testcase = TestCase.query.filter_by(
        version_id=version.id,
        code="TC_BT_001",
    ).first()
    if bluetooth_testcase is None:
        bluetooth_testcase = TestCase(
            version_id=version.id,
            title="Sample Bluetooth Reconnect Checklist",
            code="TC_BT_001",
            module="Bluetooth",
            priority="P2",
            case_type="checklist",
            precondition="Use mock paired device state only.",
            steps="Trigger sample reconnect flow and observe demo status.",
            expected_result="Reconnect result is recorded as sample data.",
            status="draft",
        )
        db.session.add(bluetooth_testcase)

    execution = TestExecution.query.filter_by(
        test_case_id=testcase.id,
        tester="Demo Tester",
    ).first()
    if execution is None:
        execution = TestExecution(
            tester="Demo Tester",
            environment="Android Demo Env",
            result="passed",
            actual_result="Demo actual result is recorded.",
            notes="Mock execution record for local demo use.",
        )
        execution.capture_test_case_snapshot(testcase)
        db.session.add(execution)
        db.session.flush()

    defect = Defect.query.filter_by(code="DEF_DEMO_001").first()
    if defect is None:
        defect = Defect(
            code="DEF_DEMO_001",
            title="Sample Audio Interruption Defect",
            description="Sample issue observed during a demo execution.",
            component="Audio",
            severity="major",
            priority="P1",
            status="open",
            reproduction_steps="Run the sample playback flow and observe demo output.",
            observed_result="Demo audio output is interrupted.",
            reporter="Demo Reporter",
        )
        defect.capture_execution_snapshot(execution)
        db.session.add(defect)

    log_file = LogFile.query.filter_by(
        project_id=project.id,
        filename="sample_audio_check.log",
    ).first()
    if log_file is None:
        log_file = LogFile(
            project_id=project.id,
            version_id=version.id,
            filename="sample_audio_check.log",
            category="sample",
            storage_path="mock/logs/sample_audio_check.log",
            uploaded_by="demo_tester",
            notes="Mock log metadata only.",
        )
        db.session.add(log_file)

    db.session.commit()


def register_login_loader():
    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        if not user_id.isdigit():
            return None
        return db.session.get(User, int(user_id))
