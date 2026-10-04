"""Formal wrappers preserve methods while tracking the real SDK boundary."""

from pathlib import Path
from types import SimpleNamespace

from openai import APIError, OpenAI

from experiment import adapters
from experiment.framework import _is_safe
from experiment.normalization import transcribe
from app.services.ai.exceptions import AIConfigurationError, AIProviderError, AIResponseError
from app.services.test_design.prompts import build_test_design_messages


class _GateError(Exception):
    pass


class _Proposed(adapters.ProposedAdapter):
    def __init__(self, owner, *args, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)

    def _export(self, record, run, context, version_id):
        try:
            expected_chars = sum(len(item["content"]) for item in self.owner._expected["messages"])
            if run.max_tokens != 8000 or run.temperature is not None or run.input_chars != expected_chars:
                raise _GateError("Generation metadata differs from the frozen request.")
            return super()._export(record, run, context, version_id)
        except Exception:
            self.owner._framework = True
            raise

    def _provider(self):
        provider = super()._provider()
        original = provider.generate
        def generate(context):
            try:
                return original(context)
            except (AIResponseError, AIProviderError, AIConfigurationError):
                raise
            except Exception:
                self.owner._framework = True
                raise
        provider.generate = generate
        return provider


class FormalAdapters:
    def __init__(self, output: Path, settings: dict, before_call, client_factory=None):
        self.output = Path(output)
        self.settings = adapters._settings(settings)
        if self.settings['timeout_seconds'] != 60 or self.settings['max_output_tokens'] != 8000:
            raise ValueError('Frozen formal request settings are required.')
        if not callable(before_call):
            raise ValueError('A persistent call marker is required.')
        self.before_call = before_call
        self.client_factory = client_factory
        self._framework = False
        self._sdk_error = False
        self._output_unsafe = False
        self._calls = 0
        self._expected = None
        self._closed = False
        self.baseline = adapters.BaselineAdapter(self.settings, client_factory=self._client)
        self.proposed = _Proposed(self, self.settings, self.output / 'proposed.sqlite3', client_factory=self._client)

    def _reject(self):
        self._framework = True
        raise _GateError('Formal SDK boundary validation failed.')

    def _client(self, **kwargs):
        if kwargs.get('max_retries') != 0 or kwargs.get('timeout') != 60:
            self._reject()
        try:
            factory = self.client_factory if self.client_factory is not None else OpenAI
            client = factory(**kwargs)
            if getattr(client, 'max_retries', 0) != 0:
                self._reject()
            actual_create = client.chat.completions.create
        except Exception:
            self._framework = True
            raise
        def create(**request):
            if self._calls or request != self._expected:
                self._reject()
            try:
                self.before_call()
            except Exception:
                self._framework = True
                raise _GateError('Formal call evidence could not be persisted.') from None
            self._calls = 1
            try:
                response = actual_create(**request)
                choices = getattr(response, "choices", None)
                message = getattr(choices[0], "message", None) if choices else None
                content = getattr(message, "content", None)
                if isinstance(content, str) and not _is_safe(content, self.settings):
                    self._output_unsafe = True
                return response
            except APIError:
                self._sdk_error = True
                raise
            except Exception:
                self._framework = True
                raise _GateError('Unexpected SDK call failure.') from None
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
                               close=getattr(client, 'close', lambda: None))

    def _failure(self, record=None):
        record = record or {}
        record.update(status='framework_error', failure_origin='framework', sdk_calls=self._calls,
                      error_type='FormalFrameworkError', error_message='Formal experiment framework validation failed safely.',
                      initial_text=None, initial_cases=[], structured_output=None)
        record.pop('normalization', None)
        return record

    def generate(self, method, *, title, requirement_text) -> dict:
        self._calls = 0
        self._framework = False
        self._sdk_error = False
        self._output_unsafe = False
        if self._closed or method not in {'baseline', 'proposed'}:
            return self._failure()
        try:
            context = adapters._context({'title': title, 'requirement_text': requirement_text}, adapters._config(self.settings))
            messages = (adapters._baseline_messages(context.model_dump(mode='json')) if method == 'baseline'
                        else build_test_design_messages(context))
            self._expected = dict(model=self.settings['model'], messages=messages, max_tokens=8000,
                                  stream=False, extra_body={'thinking': {'type': 'disabled'}})
            if method == 'proposed':
                self._expected['response_format'] = {'type': 'json_object'}
            record = getattr(self, method).generate({'title': title, 'requirement_text': requirement_text})
            if (self._framework or record['status'] == 'pre_call_failed'
                    or record.get('error_type') in {'EvidenceValidationError', 'WorkflowPersistenceError'}
                    or (record['status'] != 'succeeded' and record.get('error_type') == 'AIProviderError' and not self._sdk_error)
                    or self._calls != 1):
                return self._failure(record)
            if self._output_unsafe:
                record.update(status='failed', initial_text=None, initial_cases=[], structured_output=None,
                              error_type='AIResponseError', error_message='Method output failed safety validation.')
            if not _is_safe(record, self.settings) or adapters._unsafe(record, adapters._config(self.settings)):
                return self._failure(record)
            if method == 'baseline' and record['status'] == 'succeeded':
                raw = record['initial_text']
                if not _is_safe(raw, self.settings):
                    record.update(status='failed', initial_text=None, error_type='AIResponseError',
                                  error_message='Baseline output failed safety validation.')
                else:
                    record['normalization'] = transcribe(raw)
                    record['initial_cases'] = record['normalization']['normalized']
                    if not record['normalization']['usable']:
                        record.update(status='failed', error_type='BaselineParseError',
                                      error_message='Baseline output has no usable explicitly labeled case.')
            record.update(sdk_calls=self._calls, failure_origin=None if record['status'] == 'succeeded' else 'method')
            return record
        except Exception:
            return self._failure()

    def close(self):
        self._closed = True
        self.baseline.close()
        self.proposed.close()
