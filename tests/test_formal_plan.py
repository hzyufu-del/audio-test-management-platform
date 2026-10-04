import copy
import builtins
import hashlib
import json
import shutil

import pytest

from experiment import formal_plan as fp


def test_default_plan_is_paired_and_reference_free():
    plan = fp.build_formal_plan()
    assert plan['formal_experiment'] is True
    assert plan['ready_to_execute'] is True
    assert plan['provider_calls_allowed'] is False
    assert plan['provider_calls'] == plan['actual_provider_calls'] == 0
    assert plan['planned_pairs'] == 56
    assert plan['requirements_count'] == 28
    assert len(plan['tasks']) == 56
    assert len({(t['requirement_id'], t['method']) for t in plan['tasks']}) == 56
    assert all(t['attempt_no'] == 1 for t in plan['tasks'])
    assert all(set(t['input']) == {'title', 'requirement_text'} for t in plan['tasks'])
    assert 'reference_scenarios' not in plan
    for start in range(0, 28, 4):
        assert [r['method_order'] for r in plan['requirements'][start:start + 4]] == [
            ['baseline', 'proposed'], ['proposed', 'baseline']] * 2
    assert all(len(h) == 64 for h in plan['prompt_hashes'].values())
    fp.validate_formal_plan(plan)


@pytest.mark.parametrize('field', ['tasks', 'requirements', 'dataset_sha256',
                                  'parameters', 'prompt_hashes', 'source_evidence'])
def test_plan_mutation_rejected(field):
    plan = fp.build_formal_plan()
    plan[field] = []
    with pytest.raises(fp.FormalPlanError):
        fp.validate_formal_plan(plan)


def test_hashes_are_frozen_and_sentinel_reference_stays_private(tmp_path, monkeypatch):
    shutil.copytree(fp.DEFAULT_DATASET_DIR, tmp_path / 'data')
    directory = tmp_path / 'data'
    reference = directory / 'reference_scenarios.jsonl'
    rows = [json.loads(line) for line in reference.read_text(encoding='utf-8').splitlines()]
    rows[0]['expected_behavior'] = 'REFERENCE_ONLY_SENTINEL'
    reference.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    with pytest.raises(fp.FormalPlanError):
        fp.build_formal_plan(directory)
    frozen = copy.deepcopy(fp.EXPECTED_DATASET_HASHES)
    frozen[reference.name] = hashlib.sha256(reference.read_bytes()).hexdigest()
    monkeypatch.setattr(fp, 'EXPECTED_DATASET_HASHES', frozen)
    readme = directory / 'DATASET_README.md'
    readme.write_text(readme.read_text(encoding='utf-8').replace(
        '4b7663d5a73df3676c0ff97043911a8cfb0118399dfe2c3ee965d31c2dc8b178',
        frozen[reference.name]), encoding='utf-8')
    plan = fp.build_formal_plan(directory)
    assert 'REFERENCE_ONLY_SENTINEL' not in json.dumps(plan)
    reference.write_bytes(reference.read_bytes() + b'\n')
    with pytest.raises(fp.FormalPlanError):
        fp.validate_formal_plan(plan, directory)


def test_prompt_hashes_match_existing_functions():
    from experiment.adapters import baseline_prompt_hash
    from app.services.test_design.prompts import prompt_hash

    plan = fp.build_formal_plan()
    assert plan['prompt_hashes'] == {'baseline': baseline_prompt_hash(), 'proposed': prompt_hash()}
    assert plan['prompt_versions'] == {'baseline': 'baseline-v1', 'proposed': 'test-design-v3'}
    assert plan['parameters'] == {
        'requested_model': 'deepseek-v4-pro', 'base_url': 'https://api.deepseek.com',
        'provider': 'deepseek', 'endpoint_safe_identifier': 'api.deepseek.com',
        'max_output_tokens': 8000, 'timeout_seconds': 60, 'thinking': 'disabled',
        'temperature': None, 'temperature_sent': False, 'max_retries': 0, 'stream': False,
    }


def test_dry_run_never_imports_runtime_or_creates_directories(monkeypatch):
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == 'app' or name.startswith('app.') or name in {'dotenv', 'experiment.adapters'}:
            pytest.fail('dry-run imported execution runtime')
        return real_import(name, *args, **kwargs)

    def forbidden_mkdir(*args, **kwargs):
        pytest.fail('dry-run created directory')

    monkeypatch.setattr(builtins, '__import__', guarded_import)
    monkeypatch.setattr(fp.Path, 'mkdir', forbidden_mkdir)
    fp.validate_formal_plan(fp.build_formal_plan())


def test_frozen_hashes_match_delivery_readme():
    readme = (fp.DEFAULT_DATASET_DIR / 'DATASET_README.md').read_text(encoding='utf-8')
    for name, digest in fp.EXPECTED_DATASET_HASHES.items():
        assert f'| {name} | {digest} |' in readme
    assert fp.verify_dataset_hashes() == fp.EXPECTED_DATASET_HASHES


@pytest.mark.parametrize('mutation', [
    lambda p: p['tasks'][0].update(requirement_id='REQ_UNKNOWN_001'),
    lambda p: p['tasks'][0].update(requirement_id='PILOT_AUTH_001'),
    lambda p: p['tasks'][0].update(method='unknown'),
    lambda p: p['tasks'][0].update(attempt_no=2),
    lambda p: p['tasks'][0]['input'].update(reference_scenarios=['sentinel']),
    lambda p: p['tasks'].append(copy.deepcopy(p['tasks'][0])),
    lambda p: p['tasks'].pop(),
    lambda p: p['requirements'].pop(),
    lambda p: p['parameters'].update(temperature=0.5),
    lambda p: p.update(sample_role='pilot'),
    lambda p: p.update(reference_scenarios=[]),
    lambda p: p['tasks'][0].update(requirement_hash='0' * 64),
])
def test_pair_identity_or_boundary_changes_rejected(mutation):
    plan = fp.build_formal_plan()
    mutation(plan)
    with pytest.raises(fp.FormalPlanError):
        fp.validate_formal_plan(plan)


def test_readme_hash_drift_rejected(tmp_path):
    shutil.copytree(fp.DEFAULT_DATASET_DIR, tmp_path / 'data')
    directory = tmp_path / 'data'
    readme = directory / 'DATASET_README.md'
    text = readme.read_text(encoding='utf-8')
    readme.write_text(text.replace(fp.EXPECTED_DATASET_HASHES['requirements.jsonl'], '0' * 64),
                      encoding='utf-8')
    with pytest.raises(fp.FormalPlanError):
        fp.verify_dataset_hashes(directory)


@pytest.mark.parametrize('target', ['baseline', 'proposed'])
def test_current_template_cannot_redefine_frozen_baseline(monkeypatch, target):
    original = fp._template_constants

    def changed(path, names):
        result = original(path, names)
        key = 'BASELINE_PROMPT' if target == 'baseline' else 'TEST_DESIGN_SYSTEM_PROMPT'
        if key in result:
            result[key] += ' Changed template'
        return result

    monkeypatch.setattr(fp, '_template_constants', changed)
    with pytest.raises(fp.FormalPlanError):
        fp.build_formal_plan()


def test_current_version_cannot_redefine_frozen_baseline(monkeypatch):
    monkeypatch.setattr(fp, 'PROMPT_VERSION', 'test-design-v4')
    with pytest.raises(fp.FormalPlanError):
        fp.build_formal_plan()


def test_frozen_artifacts_are_recorded_and_pinned():
    plan = fp.build_formal_plan()
    assert plan['frozen_artifacts_sha256'] == {
        'experiment/normalization_policy.json':
            'e9ef7c808bb9fd25c6490fefa9acb6de5a5b55ef5d403f62afb85b519a552540',
        'docs/experiment-design.md':
            '623bb3c4be122cc107500b8393b401790d7182fd096a8f939eaa24ebd7b946dc',
    }


@pytest.mark.parametrize('path', ['experiment/normalization_policy.json', 'docs/experiment-design.md'])
def test_frozen_artifact_drift_rejected_without_editing_original(monkeypatch, path):
    plan = fp.build_formal_plan()
    original = fp.Path.read_bytes

    def altered_bytes(self):
        result = original(self)
        if self.as_posix().endswith(path):
            return result + b'\nchanged'
        return result

    monkeypatch.setattr(fp.Path, 'read_bytes', altered_bytes)
    with pytest.raises(fp.FormalPlanError):
        fp.build_formal_plan()
    with pytest.raises(fp.FormalPlanError):
        fp.validate_formal_plan(plan)
