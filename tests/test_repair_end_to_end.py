"""Request-level acceptance with real isolated SQLite persistence, no sockets."""
from html.parser import HTMLParser

from app import create_app
from app.extensions import db
from app.models import GenerationRun, Project, ReviewRecord, TestCase as Case, TestCaseDraft as Draft, User, Version


class Inputs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'input' and attrs.get('name'):
            self.values[attrs['name']] = attrs.get('value', '')


def inputs(response):
    parsed = Inputs()
    parsed.feed(response.get_data(as_text=True))
    return parsed.values


def test_generation_review_save_reopen_database_and_replay(tmp_path):
    config = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (tmp_path / 'roundtrip.sqlite').as_posix(),
        'AI_PROVIDER': 'mock', 'AI_ENABLED': False, 'AI_CONFIG_ERROR': '',
        'DEEPSEEK_API_KEY': '', 'DEEPSEEK_MODEL': '', 'SECRET_KEY': 'demo-roundtrip-key',
    }
    app = create_app(config)
    with app.app_context():
        db.create_all()
        p = Project(code='DEMO-ROUNDTRIP', name='Demo audio project')
        reviewer = User(username='Demo reviewer', email='roundtrip@example.test')
        reviewer.set_password('demo-password')
        db.session.add_all([p, reviewer])
        db.session.flush()
        v = Version(project_id=p.id, code='DEMO-V1', name='Demo version')
        db.session.add(v)
        db.session.commit()
        project_id, version_id = p.id, v.id

    client = app.test_client()
    login = client.post('/auth/login', data={'email':'roundtrip@example.test', 'password':'demo-password'})
    assert login.status_code == 302
    form = client.get('/ai-test-design/new')
    assert form.status_code == 200 and b'mock' in form.data.lower()
    token = inputs(form)['request_key']
    payload = dict(project_id=project_id, version_id=version_id,
                   title='Demo audio volume', requirement_text='Demo volume control supports bounded volume and visible status.',
                   request_key=token)
    generated = client.post('/ai-test-design/new', data=payload)
    assert generated.status_code == 302
    replay = client.post('/ai-test-design/new', data=payload)
    assert replay.status_code == 302 and replay.location == generated.location
    assert client.get(generated.location).status_code == 200
    with app.app_context():
        run = GenerationRun.query.one()
        assert run.status == 'succeeded' and run.provider == 'mock'
        run_id, session_id = run.id, run.session_id
        first, second = run.session.drafts[:2]
        draft_id, reject_id = first.id, second.id
        content = {field:getattr(first, field) for field in (
            'suggested_code','title','module','priority','case_type','scenario_type','precondition','steps','expected_result')}
        content['precondition'] = content['precondition'] or ''
    edit_form = client.get(f'/ai-test-design/drafts/{draft_id}/edit')
    versions = inputs(edit_form)
    content.update(title='Demo reviewer revised volume case', comment='Demo reviewed against sample requirement',
                   draft_revision=versions['draft_revision'], session_revision=versions['session_revision'])
    edited = client.post(f'/ai-test-design/drafts/{draft_id}/edit', data=content)
    assert edited.status_code == 302
    fresh_versions = inputs(client.get(f'/ai-test-design/drafts/{draft_id}/edit'))
    accepted = client.post(f'/ai-test-design/drafts/{draft_id}/accept', data={
        k:fresh_versions[k] for k in ('draft_revision','session_revision')})
    assert accepted.status_code == 302
    reject_versions = inputs(client.get(f'/ai-test-design/drafts/{reject_id}/edit'))
    rejected = client.post(f'/ai-test-design/drafts/{reject_id}/reject', data={
        k:reject_versions[k] for k in ('draft_revision','session_revision')})
    assert rejected.status_code == 302
    # End all original DB connections; reopen with a new application instance.
    with app.app_context():
        db.session.remove()
        db.engine.dispose()
    reopened = create_app(config)
    with reopened.app_context():
        draft = db.session.get(Draft,draft_id)
        case = db.session.get(Case,draft.accepted_test_case_id)
        assert draft.status == 'accepted' and case.title == content['title']
        assert case.status == 'draft'  # Acceptance is not execution or activation.
        assert draft.generation_run_id == run_id
        assert db.session.get(Draft,reject_id).status == 'rejected'
        assert [r.action for r in draft.review_records] == ['edit','accept']
        assert ReviewRecord.query.count() == 3
        assert GenerationRun.query.count() == 1
        case_id = case.id
    reader = reopened.test_client()
    assert reader.get(f'/ai-test-design/{session_id}').status_code == 200
    assert reader.get(f'/ai-test-design/runs/{run_id}').status_code == 200
    assert reader.get(f'/test-cases/{case_id}').status_code == 200
