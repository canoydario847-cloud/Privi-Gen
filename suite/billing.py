"""Use Privi Guard prepaid credits; no new wallet, ledger, or mock paid mode."""
import hashlib
import http.client
import json
from datetime import datetime, timezone
import urllib.error
import urllib.request
import uuid

from privi_pr_guard import GuardError, NoRedirect, request_check, summarize
from .engine import canonical

def paid_plan(key, expected_org):
    """An included check counts as paid only with current server-side entitlement."""
    if not isinstance(expected_org,str) or not expected_org:
        raise GuardError('Receipt is missing organization binding')
    request = urllib.request.Request(
        'https://privi-ledger-aqe5.onrender.com/mcp',
        data=json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/call',
                         'params':{'name':'ledger_plan','arguments':{}}}).encode(),
        headers={'Authorization':f'Bearer {key}','Content-Type':'application/json',
                 'Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-06-18'},method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=30) as response:
            raw=response.read(100_001)
        if len(raw)>100_000: raise ValueError
        text=raw.decode()
        if text.lstrip().startswith('{'):
            rpc=json.loads(text)
        else:
            messages=[json.loads(line[5:].strip()) for line in text.splitlines() if line.startswith('data:')]
            rpc=next(m for m in messages if m.get('id')==1)
        if rpc.get('id')!=1 or 'error' in rpc: raise ValueError
        result=rpc['result']
        if result.get('isError'): raise ValueError
        plan=result.get('structuredContent')
        if not isinstance(plan,dict) or 'plan' not in plan:
            plan=json.loads(next(c['text'] for c in result['content'] if c.get('type')=='text'))
        if plan['org_id']!=expected_org or plan['plan'] not in ('pro','enterprise'): raise ValueError
        if plan['plan']=='pro':
            expires=datetime.fromisoformat(plan['paid_until'].replace('Z','+00:00'))
            if expires.tzinfo is None or expires<=datetime.now(timezone.utc): raise ValueError
        return {'plan':plan['plan'],'paid_until':plan.get('paid_until')}
    except (OSError,http.client.HTTPException,ValueError,KeyError,TypeError,StopIteration,AttributeError):
        raise GuardError('Included checks require a verified active paid plan; free allowance does not unlock this service') from None


def charge(key, service, policy_sha256, arguments):
    text = canonical({'service':service,'policy_sha256':policy_sha256,'arguments':arguments})
    if len(text) > 100_000:
        raise GuardError('Input exceeds the fixed two-credit billing size')
    request_id = uuid.uuid4().hex
    source = f'privi-suite:{service}:{request_id}'
    payload = {'items':[{'text':text,'direction':d,'source':source} for d in ('inbound','outbound')]}
    digest = hashlib.sha256(text.encode()).hexdigest()
    response = request_check(payload,key)
    receipt = summarize({'patch_sha256':digest},payload,response)
    entitlement = None
    if any(c['paid_by']=='free' for c in receipt['checks']):
        orgs = [r['receipt']['body'].get('org_id') for r in response['results']]
        if not orgs[0] or any(org != orgs[0] for org in orgs):
            raise GuardError('Receipt is missing consistent organization binding')
        entitlement = paid_plan(key,orgs[0])
    if receipt['verdict'] != 'allow':
        raise GuardError('Privi Guard flagged the input; credits may have been consumed, no policy report issued')
    return {'provider':'Privi Guard','check_units':2,
            'credit_units':sum(c['paid_by']=='credits' for c in receipt['checks']),
            'paid_plan':entitlement,'request_id':request_id,
            'request_sha256':digest,'checks':receipt['checks'],
            'verification':'HTTPS provider response plus receipt body/input binding; no independent signature or chain verification'}
