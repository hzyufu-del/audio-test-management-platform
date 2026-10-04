"""Dependency-free formal preview; no credentials, application or writes."""
from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

from experiment import framework
from test_design_contract import PROMPT_VERSION

DEFAULT_DATASET_DIR = framework.ROOT / 'experiment' / 'dataset'
EXPECTED_DATASET_HASHES = {
    'requirements.jsonl': '7eaf3c824d35318f910c2134adbd0f5e2314ff6d56a7a04a00c96f4aea67c6d7',
    'reference_scenarios.jsonl': '4b7663d5a73df3676c0ff97043911a8cfb0118399dfe2c3ee965d31c2dc8b178',
}
EXPECTED_PROMPT_VERSIONS = {'baseline': 'baseline-v1', 'proposed': 'test-design-v3'}
EXPECTED_PROMPT_HASHES = {
    'baseline': 'ec5f5690c0e6ada964cafe3a8903ab070269733c3b87363eeef2a7e450859dd3',
    'proposed': '1ce470e27c23fea69d0554dedb3d4a88f16053af3fb44f166181b9f01bd3cf9f',
}
EXPECTED_FROZEN_ARTIFACT_HASHES = {
    'experiment/normalization_policy.json':
        'e9ef7c808bb9fd25c6490fefa9acb6de5a5b55ef5d403f62afb85b519a552540',
    'docs/experiment-design.md':
        '623bb3c4be122cc107500b8393b401790d7182fd096a8f939eaa24ebd7b946dc',
}


class FormalPlanError(framework.ExperimentError):
    """A fixed public failure without source or dataset content."""


def verify_dataset_hashes(dataset_dir=None):
    """Verify original file bytes against the frozen v1.0 README hashes."""
    directory = Path(dataset_dir) if dataset_dir is not None else DEFAULT_DATASET_DIR
    try:
        readme = (directory / 'DATASET_README.md').read_text(encoding='utf-8')
        entries = re.findall(r'^\|\s*(requirements\.jsonl|reference_scenarios\.jsonl)\s*\|\s*([a-f0-9]{64})\s*\|\s*$',
                             readme, flags=re.MULTILINE)
        if ('数据集版本：**v1.0**' not in readme or len(entries) != 2
                or dict(entries) != EXPECTED_DATASET_HASHES):
            raise ValueError
        hashes = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                  for name in EXPECTED_DATASET_HASHES}
        if hashes != EXPECTED_DATASET_HASHES:
            raise ValueError
        return hashes
    except (OSError, TypeError, ValueError, UnicodeError):
        raise FormalPlanError('Formal dataset does not match frozen v1.0 files.') from None


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _frozen_artifact_hashes():
    hashes = {name: hashlib.sha256((framework.ROOT / name).read_bytes()).hexdigest()
              for name in EXPECTED_FROZEN_ARTIFACT_HASHES}
    if hashes != EXPECTED_FROZEN_ARTIFACT_HASHES:
        raise ValueError
    return hashes


def _template_constants(path, names):
    """Interpret only literal template expressions; never execute source code."""
    values = {}

    def evaluate(node):
        if isinstance(node, ast.Name) and node.id in values:
            return values[node.id]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return evaluate(node.left) + evaluate(node.right)
        if isinstance(node, ast.Call) and not node.keywords:
            if isinstance(node.func, ast.Name) and node.func.id == '_canonical_json' and len(node.args) == 1:
                return _canonical(evaluate(node.args[0]))
            if (isinstance(node.func, ast.Attribute) and node.func.attr == 'strip'
                    and not node.args):
                value = evaluate(node.func.value)
                if isinstance(value, str):
                    return value.strip()
            raise ValueError
        return ast.literal_eval(node)

    tree = ast.parse(path.read_text(encoding='utf-8'))
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if isinstance(target, ast.Name) and target.id in names:
                values[target.id] = evaluate(statement.value)
    if set(values) != set(names):
        raise ValueError
    return values


def _prompt_metadata():
    root = framework.ROOT
    baseline = _template_constants(root / 'experiment' / 'adapters.py',
                                   {'BASELINE_PROMPT', 'BASELINE_PROMPT_VERSION'})
    proposed = _template_constants(root / 'app' / 'services' / 'test_design' / 'prompts.py',
                                   {'TEST_DESIGN_JSON_EXAMPLE', 'TEST_DESIGN_SYSTEM_PROMPT'})
    context = _canonical({'title': '{title}', 'requirement_text': '{requirement_text}'})
    templates = {
        'baseline': [{'role': 'user', 'content': baseline['BASELINE_PROMPT'] + '\n' + context}],
        'proposed': [{'role': 'system', 'content': proposed['TEST_DESIGN_SYSTEM_PROMPT']},
                     {'role': 'user', 'content': context}],
    }
    versions = {'baseline': baseline['BASELINE_PROMPT_VERSION'], 'proposed': PROMPT_VERSION}
    hashes = {name: framework.text_hash(_canonical(template)) for name, template in templates.items()}
    if versions != EXPECTED_PROMPT_VERSIONS or hashes != EXPECTED_PROMPT_HASHES:
        raise ValueError
    return versions, hashes


def build_formal_plan(dataset_dir=None):
    """Build 56 immutable pair inputs with reference hashes only."""
    directory = Path(dataset_dir) if dataset_dir is not None else DEFAULT_DATASET_DIR
    try:
        frozen_artifacts = _frozen_artifact_hashes()
        hashes = verify_dataset_hashes(directory)
        dataset = framework.load_dataset(directory, role='formal_plan')
        if dataset['dataset_sha256'] != hashes:
            raise ValueError
        plan = framework.build_plan(dataset, role='formal_plan')
        del plan['reference_scenarios']
        versions, prompt_hashes = _prompt_metadata()
        plan.update(
            plan_version='formal-experiment-v1', formal_experiment=True, formal_eligible=False,
            execution_mode='dry_run', provider_calls_allowed=False, provider_calls=0,
            actual_provider_calls=0, planned_pairs=56, requirements_count=28,
            ready_to_execute=True, prompt_versions=versions, prompt_hashes=prompt_hashes,
            frozen_artifacts_sha256=frozen_artifacts,
            parameters={'requested_model': 'deepseek-v4-pro', 'base_url': 'https://api.deepseek.com',
                        'provider': 'deepseek', 'endpoint_safe_identifier': 'api.deepseek.com',
                        'max_output_tokens': 8000, 'timeout_seconds': 60, 'thinking': 'disabled',
                        'temperature': None, 'temperature_sent': False, 'max_retries': 0,
                        'stream': False},
        )
        return plan
    except (framework.ExperimentError, OSError, TypeError, ValueError, SyntaxError):
        raise FormalPlanError('Formal plan could not be verified safely.') from None


def validate_formal_plan(plan, dataset_dir=None):
    """Rebuild current inputs, order, template hashes and source evidence."""
    expected = build_formal_plan(dataset_dir)
    try:
        if not isinstance(plan, dict) or _canonical(plan) != _canonical(expected):
            raise ValueError
    except (TypeError, ValueError):
        raise FormalPlanError('Formal plan differs from the frozen verified plan.') from None
