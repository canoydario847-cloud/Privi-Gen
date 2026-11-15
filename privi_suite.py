#!/usr/bin/env python3
"""100 paid Privi policy services for GitHub, AI and call networks. Python 3.10+."""
import argparse
import json
import os
from pathlib import Path
import sys

from privi_pr_guard import GuardError
from suite.catalog import CATALOG
from suite.engine import InputError, MAX_INPUT_BYTES, strict_json
from suite.runner import PaymentRequired, Runner, tools

MAX_LINE = 100_000


def serve(runner, stdin=None, stdout=None):
    """Sequential newline-delimited MCP stdio. No paid tools before initialization."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    initialized = False
    while True:
        line = stdin.readline(MAX_LINE+1)
        if not line:
            return
        if len(line)>MAX_LINE:
            # Terminate on oversized frames rather than interpreting their tail.
            return
        ident = None
        try:
            message = strict_json(line)
            if not isinstance(message,dict) or message.get('jsonrpc')!='2.0' or not isinstance(message.get('method'),str):
                raise InputError('Invalid JSON-RPC request')
            ident = message.get('id')
            if ident is not None and (type(ident) not in (int,str)):
                raise InputError('Invalid request ID')
            if 'id' not in message:
                continue  # Notifications never execute billable calls.
            method = message['method']
            params = message.get('params',{})
            if not isinstance(params,dict):
                raise InputError('Invalid request parameters')
            if method=='initialize':
                version = params.get('protocolVersion')
                result = {'protocolVersion':version if version in ('2025-03-26','2025-06-18','2025-11-25') else '2025-06-18',
                          'capabilities':{'tools':{'listChanged':False}},
                          'serverInfo':{'name':'privi-paid-suite','version':'1.0.1'},
                          'instructions':'100 paid policy checks of supplied evidence. Discovery is free; execution requires prepaid Privi Guard credits or verified paid-plan allowance, and explicit session authorization.'}
                initialized = True
            elif method=='ping':
                result = {}
            elif not initialized:
                raise InputError('Initialize before using tools')
            elif method=='tools/list':
                if params.get('cursor'):
                    raise InputError('Unknown tools cursor')
                result = {'tools':tools()}
            elif method=='tools/call':
                try:
                    report = runner.call(params.get('name'),params.get('arguments',{}))
                    result = {'content':[{'type':'text','text':json.dumps(report)}],
                              'structuredContent':report,'isError':False}
                except (InputError,PaymentRequired,GuardError) as exc:
                    result = {'content':[{'type':'text','text':str(exc)}],'isError':True}
            else:
                stdout.write(json.dumps({'jsonrpc':'2.0','id':ident,'error':{'code':-32601,'message':'Method not found'}})+'\n')
                stdout.flush()
                continue
            response = {'jsonrpc':'2.0','id':ident,'result':result}
        except (InputError,ValueError,RecursionError):
            response = {'jsonrpc':'2.0','id':ident,'error':{'code':-32600,'message':'Invalid or out-of-sequence request'}}
        stdout.write(json.dumps(response)+'\n')
        stdout.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enable-paid',action='store_true')
    parser.add_argument('--max-session-units',type=int,default=0)
    sub = parser.add_subparsers(dest='command',required=True)
    sub.add_parser('list')
    show = sub.add_parser('describe')
    show.add_argument('service',choices=list(CATALOG))
    run = sub.add_parser('run')
    run.add_argument('service',choices=list(CATALOG))
    run.add_argument('--input',type=Path,required=True)
    sub.add_parser('mcp')
    args = parser.parse_args(argv)
    try:
        runner = Runner(os.getenv('PRIVI_API_KEY',''),enable_paid=args.enable_paid,max_session_units=args.max_session_units)
        if args.command=='list':
            result = {'services':tools(),'count':len(CATALOG),'execution':'paid_only'}
        elif args.command=='describe':
            s = CATALOG[args.service]
            result = {**next(t for t in tools() if t['name']==args.service),'example':s['example'],'rules':s['rules']}
        elif args.command=='mcp':
            serve(runner)
            return 0
        else:
            with args.input.open('rb') as stream:
                raw = stream.read(MAX_INPUT_BYTES+1)
            if len(raw)>MAX_INPUT_BYTES:
                raise InputError('Input exceeds 64,000 bytes')
            result = runner.call(args.service,strict_json(raw))
        print(json.dumps(result,indent=2))
        return 2 if result.get('decision')=='review' else 0
    except (InputError,PaymentRequired,GuardError) as exc:
        print(json.dumps({'status':'error','message':str(exc)}))
        return 1
    except OSError:
        print(json.dumps({'status':'error','message':'Local input could not be read'}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
