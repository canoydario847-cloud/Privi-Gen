#!/usr/bin/env python3
"""Regenerate public discovery catalog and human-readable policy matrix."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from suite.catalog import CATALOG
from suite.engine import policy_hash, schema_for


def artifacts():
    services=[]
    lines=['# Privi: 100 paid policy services','',
           'All services evaluate caller-supplied evidence. Two Guard check units per execution, funded by credits or verified paid-plan allowance; see [billing and scope](paid-suite.md).',
           '', 'Catalog discovery is free; policy execution through the supported runner is paid-only. No live data collection or exclusivity is implied.', '']
    n=0
    for domain,title in [('github','GitHub — 35 services'),('ai','AI agents — 35 services'),('calls','Call networks — 30 services')]:
        lines += ['## '+title,'','| # | Service ID | Inputs | Policy |','| --- | --- | --- | --- |']
        for s in CATALOG.values():
            if s['domain'] != domain: continue
            n+=1
            rules=' '.join(r[3] for r in s['rules'])
            lines.append(f"| {n} | `{s['name']}` | {', '.join('`'+f+'`' for f in s['fields'])} | {rules} |")
            services.append({k:s[k] for k in ('name','title','domain','version','credit_units','rules','example')} |
                            {'inputSchema':schema_for(s),'policy_sha256':policy_hash(s)})
        lines.append('')
    return {'suite/catalog.json':json.dumps({'schema_version':1,'count':100,'execution':'paid_only','services':services},indent=2)+'\n',
            'docs/paid-service-catalog.md':'\n'.join(lines)}


if __name__=='__main__':
    for path,text in artifacts().items():
        (ROOT/path).write_text(text)
