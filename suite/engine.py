"""Pure bounded policy evaluation. Only the paid dispatcher exposes this to clients."""
from collections import Counter
import hashlib
import json
import math
import re

from .catalog import CATALOG

MAX_INPUT_BYTES = 64_000


class InputError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise InputError('Duplicate JSON keys are not accepted')
            result[key] = value
        return result
    def constant(_):
        raise InputError('Non-finite JSON numbers are not accepted')
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, RecursionError, UnicodeError):
        raise InputError('Invalid JSON input') from None


def schema_for(spec):
    def field(kind):
        if kind == 'bool':
            return {'type': 'boolean'}
        if kind in ('int', 'positive_int'):
            return {'type': 'integer', 'minimum': int(kind == 'positive_int'), 'maximum': 10**12}
        if kind in ('number', 'positive_number', 'percent', 'unit'):
            result = {'type': 'number', 'minimum': 0, 'maximum': {'percent':100, 'unit':1}.get(kind, 10**12)}
            if kind == 'positive_number':
                result.pop('minimum')
                result['exclusiveMinimum'] = 0
            return result
        if kind in ('sha', 'digest'):
            return {'type': 'string', 'pattern': '^[0-9a-f]{' + ('40' if kind == 'sha' else '64') + '}$'}
        if kind == 'string':
            return {'type': 'string', 'minLength': 1, 'maxLength': 512}
        if kind == 'strings':
            return {'type': 'array', 'maxItems': 1024, 'items': field('string')}
        if kind == 'numbers':
            return {'type': 'array', 'minItems': 1, 'maxItems': 1024, 'items': field('number')}
        raise InputError('Unknown field type')
    return {'type':'object', 'additionalProperties':False,
            'required':list(spec['fields']),
            'properties':{k:field(v) for k,v in spec['fields'].items()}}


def valid_type(value, kind):
    if kind == 'bool':
        return type(value) is bool
    if kind in ('int','positive_int'):
        return type(value) is int and (1 if kind == 'positive_int' else 0) <= value <= 10**12
    if kind in ('number','positive_number','percent','unit'):
        return (type(value) in (int,float) and math.isfinite(value)
                and 0 <= value <= {'percent':100,'unit':1}.get(kind,10**12)
                and (kind != 'positive_number' or value > 0))
    if kind in ('string','sha','digest'):
        if not isinstance(value,str) or not 1 <= len(value) <= 512:
            return False
        try:
            value.encode('utf-8')
        except UnicodeEncodeError:
            return False
        if kind == 'string':
            return True
        return bool(re.fullmatch(r'[0-9a-f]{' + ('40' if kind == 'sha' else '64') + '}',value))
    if kind in ('strings','numbers'):
        return (isinstance(value,list) and (0 if kind=='strings' else 1) <= len(value) <= 1024
                and all(valid_type(v,'string' if kind=='strings' else 'number') for v in value))
    return False


def validate(name, arguments):
    if not isinstance(name,str) or name not in CATALOG:
        raise InputError('Unknown Privi service')
    spec = CATALOG[name]
    if not isinstance(arguments,dict) or set(arguments) != set(spec['fields']):
        raise InputError('Provide exactly the fields in the service input schema')
    for key, kind in spec['fields'].items():
        if not valid_type(arguments[key],kind):
            raise InputError(f'Invalid field: {key}; expected {kind}')
    if len(canonical(arguments).encode()) > MAX_INPUT_BYTES:
        raise InputError('Input exceeds 64,000 bytes')
    return spec


def measure(data, rule):
    key, op, target, _ = rule
    v = data[key]
    if op == 'eq': return v == target, None
    if op == 'ge': return v >= target, v
    if op == 'gt': return v > target, v
    if op == 'le': return v <= target, v
    if op == 'same': return v == data[target], None
    if op == 'ge_field': return v >= data[target], v
    if op == 'le_field': return v <= data[target], v
    if op == 'subset': return set(v) <= set(data[target]), len(set(v)-set(data[target]))
    if op == 'disjoint': return not set(v)&set(data[target]), len(set(v)&set(data[target]))
    if op == 'intersects': return bool(set(v)&set(data[target])), len(set(v)&set(data[target]))
    if op == 'full_shas': return all(re.fullmatch('[0-9a-f]{40}',x) for x in v), None
    if op == 'not_both': return not (v and data[target]), None
    if op == 'requires': return not v or data[target] is True, None
    if op == 'either': return bool(v or data[target]), None
    if op == 'forbid_unless': return not (v and data[target[0]]) or data[target[1]] is True, None
    if op in ('ratio_le','ratio_ge','ratio_le_field','ratio_ge_field'):
        fraction = v / data[target[0]]
        limit = data[target[1]] if op.endswith('_field') else target[1]
        return (fraction <= limit if op.startswith('ratio_le') else fraction >= limit), fraction
    if op == 'product_le':
        product = v * data[target[0]]
        return product <= data[target[1]], product
    if op in ('sum_le','sum_lt'):
        total = v + data[target[0]]
        return (total <= data[target[1]] if op=='sum_le' else total < data[target[1]]), total
    if op == 'max_repeat':
        count = max(Counter(v).values(), default=0)
        return count <= target, count
    if op == 'unique_count_ge':
        count = len(set(v))
        return count >= target, count
    if op == 'p95_le':
        p95 = sorted(v)[math.ceil(len(v)*0.95)-1]
        return p95 <= data[target], p95
    if op == 'increasing': return all(a<b for a,b in zip(v,v[1:])), None
    if op == 'max_share_le':
        total = sum(v)
        if total == 0: return False, None
        share = max(v)/total
        return share <= data[target], share
    raise InputError('Unsupported policy operation')


def evaluate(name, arguments):
    """Internal implementation, not an entitlement boundary for copied source."""
    spec = validate(name, arguments)
    findings, measurements = [], {}
    for index, rule in enumerate(spec['rules'], 1):
        passed, value = measure(arguments,rule)
        code = f'{name}.R{index}'
        if value is not None:
            measurements[code] = value
        if not passed:
            findings.append({'code':code,'field':rule[0],'remediation':rule[3]})
    return {'service':name,'policy_version':spec['version'],
            'decision':'pass' if not findings else 'review',
            'findings':findings,'measurements':measurements,
            'scope':'Policy check of caller-supplied evidence, not independent verification.'}


def policy_hash(spec):
    policy = {k:spec[k] for k in ('name','version','fields','rules')}
    return hashlib.sha256(canonical(policy).encode()).hexdigest()
