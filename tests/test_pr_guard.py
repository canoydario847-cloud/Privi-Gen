import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import privi_pr_guard as guard

BASE, HEAD = 'a' * 40, 'b' * 40
PATCH = 'diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n'


class PRGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'change.diff'
        self.path.write_text(PATCH)

    def prepare(self, units=2):
        return guard.prepare(self.path, BASE, HEAD, units)

    def response(self, metadata, payload, verdict='allow'):
        results = []
        for item in payload['items']:
            cid = 'gc_' + '1' * 20
            body = {'direction': item['direction'], 'source': item['source'],
                    'verdict': verdict, 'input_sha256': metadata['patch_sha256'], 'check_id': cid}
            digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
            results.append({'direction': item['direction'], 'verdict': verdict, 'paid_by': 'credits',
                            'findings': [{'evidence': 'SECRET_DO_NOT_LOG'}],
                            'receipt': {'body': body, 'receipt_hash': digest, 'check_id': cid}})
        return {'results': results}

    def test_quote_does_not_call_remote(self):
        with patch.object(guard, 'request_check') as remote, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(guard.main(['--patch', str(self.path), '--base-sha', BASE, '--head-sha', HEAD]), 0)
        remote.assert_not_called()
        self.assertEqual(json.loads(out.getvalue())['status'], 'quote')

    def test_budget_blocks_before_network(self):
        with self.assertRaises(guard.GuardError):
            self.prepare(1)

    def test_large_patch_requires_more_credits(self):
        self.path.write_text(PATCH + '+' + 'x' * 100_000)
        with self.assertRaises(guard.GuardError):
            self.prepare()
        self.assertEqual(self.prepare(4)[0]['credit_units'], 4)

    def test_invalid_sha(self):
        with self.assertRaises(guard.GuardError):
            guard.prepare(self.path, '--help', HEAD, 2)

    def test_unsupported_patch(self):
        for content in ('', PATCH + 'GIT binary patch\n', PATCH + '+Subproject commit ' + HEAD, PATCH + '\x00'):
            self.path.write_text(content)
            with self.assertRaises(guard.GuardError):
                self.prepare()

    def test_oversize_and_invalid_utf8(self):
        for raw in (b'x' * (guard.MAX_BYTES + 1), b'\xff'):
            self.path.write_bytes(raw)
            with self.assertRaises(guard.GuardError):
                self.prepare()

    def test_valid_response_omits_source_and_evidence(self):
        metadata, payload = self.prepare()
        report = guard.summarize(metadata, payload, self.response(metadata, payload))
        self.assertEqual(report['verdict'], 'allow')
        self.assertNotIn('SECRET_DO_NOT_LOG', json.dumps(report))
        self.assertNotIn(PATCH, json.dumps(report))

    def test_incomplete_response_fails_closed(self):
        metadata, payload = self.prepare()
        for response in ({}, {'results': []}, {'results': [None, None]}, None):
            with self.assertRaises(guard.GuardError):
                guard.summarize(metadata, payload, response)

    def test_receipt_tampering_and_open_mode_rejected(self):
        metadata, payload = self.prepare()
        for field, value in [('verdict', 'allow'), ('paid_by', 'open'), ('direction', 'outbound')]:
            response = self.response(metadata, payload, 'block')
            response['results'][0][field] = value
            with self.assertRaises(guard.GuardError):
                guard.summarize(metadata, payload, response)
        response = self.response(metadata, payload)
        response['results'][0]['receipt']['body']['input_sha256'] = '0' * 64
        with self.assertRaises(guard.GuardError):
            guard.summarize(metadata, payload, response)

    def test_warn_and_block_exit_nonzero(self):
        metadata, payload = self.prepare()
        for verdict in ('warn', 'block'):
            with patch.object(guard, 'request_check', return_value=self.response(metadata, payload, verdict)), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(guard.main(['--patch', str(self.path), '--base-sha', BASE, '--head-sha', HEAD, '--submit']), 2)

    def test_missing_key_and_redirect_rejected(self):
        with self.assertRaises(guard.GuardError):
            guard.request_check({}, '')
        with self.assertRaises(guard.GuardError):
            guard.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.org')

    def test_transport_errors_do_not_leak_or_retry(self):
        fake = unittest.mock.MagicMock()
        fake.open.side_effect = guard.urllib.error.URLError('SECRET_DO_NOT_LOG')
        with patch.object(guard.urllib.request, 'build_opener', return_value=fake):
            with self.assertRaises(guard.GuardError) as exc:
                guard.request_check({}, 'key')
        self.assertNotIn('SECRET_DO_NOT_LOG', str(exc.exception))
        self.assertEqual(fake.open.call_count, 1)
