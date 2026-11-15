"""Paid-only dispatch shared by CLI and MCP; no retries and bounded session spend."""
import hashlib
from . import billing
from .engine import InputError, canonical, evaluate, policy_hash, schema_for, validate
from .catalog import CATALOG


class PaymentRequired(Exception):
    pass


class Runner:
    def __init__(self, key='', *, enable_paid=False, max_session_units=0):
        if type(max_session_units) is not int or not 0 <= max_session_units <= 200:
            raise InputError('Session limit must be an integer between 0 and 200 credit units')
        self.key = key
        self.enabled = enable_paid
        self.limit = max_session_units
        self.reserved = 0

    def call(self, name, arguments):
        spec = validate(name,arguments)  # Reject malformed inputs before any billable call.
        if not self.enabled or not self.key:
            raise PaymentRequired('Paid execution is disabled; configure a key, enable paid calls and set a session limit')
        if self.reserved + 2 > self.limit:
            raise PaymentRequired('Session credit limit reached')
        # Reserve before outbound requests. On failure keep the reservation because
        # the server may have charged even if the client lost the response.
        self.reserved += 2
        receipt = billing.charge(self.key,name,policy_hash(spec),arguments)
        report = evaluate(name,arguments)
        return {**report,'status':'paid_result','billing':receipt,
                'policy_sha256':policy_hash(spec),
                'input_sha256':hashlib.sha256(canonical(arguments).encode()).hexdigest(),
                'session_units_reserved':self.reserved}


def tools():
    return [{'name':s['name'],'title':s['title'],
             'description':f"{s['title']}: " + ' '.join(r[3] for r in s['rules']) +
                ' Paid-only: 2 Privi Guard check units; prepaid credits or verified active paid-plan allowance. Evaluates supplied evidence.',
             'inputSchema':schema_for(s),
             'annotations':{'readOnlyHint':False,'destructiveHint':False,
                            'idempotentHint':False,'openWorldHint':True}}
            for s in CATALOG.values()]
