import importlib.util
from pathlib import Path

import pytest
from app.extensions import db
from app.models import Project


def launcher():
    path = Path(__file__).resolve().parents[1] / 'scripts/run_repair_demo.py'
    spec = importlib.util.spec_from_file_location('repair_demo_launcher', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_demo_migrates_and_reuse_does_not_reseed(tmp_path):
    module = launcher()
    app, database = module.prepare_demo(storage_root=tmp_path)
    assert app.config['AI_PROVIDER'] == 'mock' and not app.config['AI_ENABLED']
    assert app.config['DEEPSEEK_API_KEY'] == ''
    with app.app_context():
        project = Project.query.first()
        project.name = 'Demo preserved user change'
        pid = project.id
        db.session.commit()
        db.session.remove()
        db.engine.dispose()
    reopened, same = module.prepare_demo(database.name, storage_root=tmp_path)
    assert same == database
    with reopened.app_context():
        assert db.session.get(Project,pid).name == 'Demo preserved user change'
        db.session.remove()
        db.engine.dispose()


def test_existing_unmarked_or_outside_database_is_refused(tmp_path):
    module = launcher()
    name = 'repair-demo-' + 'a'*32 + '.sqlite'
    database = tmp_path / name
    database.write_bytes(b'original data')
    for candidate in (name, '../outside.sqlite', 'audio_test_platform.sqlite'):
        with pytest.raises(ValueError):
            module.prepare_demo(candidate, storage_root=tmp_path)
    assert database.read_bytes() == b'original data'
