#!/usr/bin/env python3
"""Privi PR Guard: bounded, paid remote screening of a GitHub patch.

Never executes patch content. Uses existing Privi Guard credits and receipts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

API = 'https://privi-ledger-aqe5.onrender.com/guard/v1/check_many'
MAX_BYTES = 400_000
UNIT_CHARS = 100_000


class GuardError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GuardError('API redirect refused; credentials were not forwarded')


def prepare(path: Path, base: str, head: str, max_units: int) -> tuple[dict, dict]:
    for sha in (base, head):
        if not re.fullmatch(r'[0-9a-f]{40}', sha):
            raise GuardError('Base and head must be full lowercase Git commit SHAs')
    if base == head:
        raise GuardError('Base and head must differ')
    if not 1 <= max_units <= 8:
        raise GuardError('Credit limit must be between 1 and 8')
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise GuardError('Patch exceeds 400,000 bytes; split the change, do not truncate')
    try:
        patch = raw.decode('utf-8')
    except UnicodeDecodeError:
        raise GuardError('Patch must be UTF-8 text') from None
    if not patch.startswith('diff --git ') or '\x00' in patch:
        raise GuardError('Expected a nonempty Git unified diff')
    if re.search(r'^(?:Binary files .* differ|GIT binary patch|Submodule )', patch, re.M) or re.search(r'^[-+ ]Subproject commit ', patch, re.M):
        raise GuardError('Binary and submodule changes need separate review; no clean result issued')
    units = 2 * max(1, (len(patch) + UNIT_CHARS - 1) // UNIT_CHARS)
    if units > max_units:
        raise GuardError(f'Needs {units} Guard credit units; exceeds authorized limit {max_units}')
    metadata = {'schema_version': 1, 'product': 'Privi PR Guard', 'base_sha': base,
                'head_sha': head, 'patch_sha256': hashlib.sha256(raw).hexdigest(),
                'credit_units': units, 'scope': 'supplied textual diff only'}
    source = f'privi-pr-guard:{base}..{head}'
    payload = {'items': [{'text': patch, 'direction': d, 'source': source}
                         for d in ('inbound', 'outbound')]}
    return metadata, payload


def request_check(payload: dict, key: str) -> dict:
    if not key or '\n' in key or '\r' in key:
        raise GuardError('Set PRIVI_API_KEY to an authorized Guard organization key')
    req = urllib.request.Request(API, data=json.dumps(payload).encode(), headers={
        'Authorization': f'Bearer {key}', 'Content-Type': 'application/json',
        'Accept': 'application/json'}, method='POST')
    try:
        # Deliberately no retry: a lost response may already have consumed credits.
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=60) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise GuardError('Guard response exceeded size limit')
        return json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise GuardError(f'Guard HTTP {exc.code}; access/payment or service failure; no retry made') from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise GuardError('Guard response unavailable or invalid; check usage before retrying') from None


def summarize(metadata: dict, payload: dict, response: dict) -> dict:
    """Reject incomplete responses and retain only receipt metadata, never excerpts."""
    try:
        results = response['results']
        if not isinstance(results, list) or len(results) != 2:
            raise ValueError
        safe = []
        for item, result in zip(payload['items'], results):
            verdict = result['verdict']
            receipt = result['receipt']
            body = receipt['body']
            canonical = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
            if (verdict not in ('allow', 'warn', 'block')
                    or result['paid_by'] not in ('credits', 'free')
                    or result['direction'] != item['direction']
                    or body['direction'] != item['direction']
                    or body['source'] != item['source']
                    or body['verdict'] != verdict
                    or body['input_sha256'] != metadata['patch_sha256']
                    or receipt['receipt_hash'] != hashlib.sha256(canonical.encode()).hexdigest()
                    or not re.fullmatch(r'gc_[0-9a-f]{20}', receipt['check_id'])
                    or body['check_id'] != receipt['check_id']):
                raise ValueError
            safe.append({'direction': item['direction'], 'verdict': verdict,
                         'paid_by': result['paid_by'], 'check_id': receipt['check_id'],
                         'receipt_hash': receipt['receipt_hash']})
        verdict = max((r['verdict'] for r in safe), key={'allow': 0, 'warn': 1, 'block': 2}.get)
        return {**metadata, 'status': 'checked', 'verdict': verdict, 'checks': safe,
                'receipt_validation': 'body hash and input binding; signature not independently verified',
                'note': 'Pattern screening, not a full code audit or proof the change is safe.'}
    except (KeyError, TypeError, ValueError, AttributeError):
        raise GuardError('Incomplete or mismatched Guard results; no passing report issued') from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--patch', type=Path, required=True)
    parser.add_argument('--base-sha', required=True)
    parser.add_argument('--head-sha', required=True)
    parser.add_argument('--max-credit-units', type=int, default=2)
    parser.add_argument('--submit', action='store_true', help='Authorize sending the diff to Privi and consuming Guard credits')
    args = parser.parse_args(argv)
    try:
        metadata, payload = prepare(args.patch, args.base_sha, args.head_sha, args.max_credit_units)
        if not args.submit:
            print(json.dumps({**metadata, 'status': 'quote', 'remote_request_sent': False}, indent=2))
            return 0
        result = summarize(metadata, payload, request_check(payload, os.getenv('PRIVI_API_KEY', '')))
        print(json.dumps(result, indent=2))
        return 0 if result['verdict'] == 'allow' else 2
    except (GuardError, OSError) as exc:
        # Never print raw transport errors, paths, source, credentials or evidence.
        message = str(exc) if isinstance(exc, GuardError) else 'Local patch could not be read'
        print(json.dumps({'status': 'error', 'message': message}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
