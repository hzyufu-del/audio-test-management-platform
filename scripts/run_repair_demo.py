"""Start a separate Mock demo. Existing databases are never seeded or migrated."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Process-local overrides only; this launcher never loads .env or uses real AI.
os.environ.update(FLASK_SKIP_DOTENV='1', AI_ENABLED='false', AI_PROVIDER='mock')

from app import create_app  # noqa: E402


def prepare_demo(database_name=None, *, storage_root=None):
    storage = Path(storage_root) if storage_root else ROOT / 'instance'
    storage.mkdir(parents=True, exist_ok=True)
    fresh = database_name is None
    name = database_name or ('repair-demo-' + uuid.uuid4().hex + '.sqlite')
    if not re.fullmatch(r'repair-demo-[0-9a-f]{32}\.sqlite', name):
        raise ValueError('Use only the database filename printed by this launcher.')
    database = storage / name
    marker = storage / (name + '.json')
    if fresh:
        if database.exists() or marker.exists():
            raise ValueError('Refusing to replace an existing demo.')
        settings = {'format':1, 'provider':'mock', 'database':name,
                    'secret_key':secrets.token_hex(32)}
    else:
        if not database.is_file() or not marker.is_file():
            raise ValueError('This is not a prepared repair demo. Create a new one.')
        settings = json.loads(marker.read_text(encoding='utf-8'))
        if settings.get('format') != 1 or settings.get('provider') != 'mock' or settings.get('database') != name:
            raise ValueError('Demo metadata does not match. No changes made.')
        # Read-only compatibility check; never migrate an existing demo implicitly.
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        migration_config = Config()
        migration_config.set_main_option('script_location', str(ROOT / 'migrations'))
        expected = ScriptDirectory.from_config(migration_config).get_current_head()
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as connection:
            version = connection.execute('SELECT version_num FROM alembic_version').fetchone()
        if not version or version[0] != expected:
            raise ValueError('Demo schema differs from this build. Create a new demo; old data remains untouched.')
    app = create_app({
        'SQLALCHEMY_DATABASE_URI':'sqlite:///' + database.as_posix(),
        'AI_PROVIDER':'mock', 'AI_ENABLED':False, 'AI_CONFIG_ERROR':'',
        'DEEPSEEK_API_KEY':'', 'DEEPSEEK_MODEL':'', 'SECRET_KEY':settings['secret_key'],
        'DEBUG':False, 'TESTING':False,
    })
    if fresh:
        runner = app.test_cli_runner()
        for command in (['db','upgrade','--directory',str(ROOT/'migrations')], ['init-db']):
            result = runner.invoke(args=command)
            if result.exit_code:
                raise RuntimeError('New demo initialization failed; partial demo preserved for diagnosis.')
        marker.write_text(json.dumps(settings, indent=2), encoding='utf-8')
    return app, database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', help='Reuse a repair-demo-<id>.sqlite created by this launcher.')
    parser.add_argument('--port', type=int, default=5002)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Port must be between 1024 and 65535.')
    app, database = prepare_demo(args.database)
    print('Mode: Mock only; no external model API calls.')
    print('Database: ' + database.name)
    print('Login: demo@example.com / demo-password')
    print('Reuse: --database ' + database.name)
    if not args.prepare_only:
        app.run(host='127.0.0.1', port=args.port, debug=False, use_reloader=False, load_dotenv=False)


if __name__ == '__main__':
    main()
