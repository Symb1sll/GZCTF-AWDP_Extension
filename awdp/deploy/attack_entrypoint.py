"""Adapter for the previously accepted ticket target; no static production flag."""
import os
import runpy

flag = os.environ.pop('GZCTF_FLAG', None)
if not flag:
    raise SystemExit('GZCTF_FLAG is required')
os.environ['TICKET_FLAG'] = flag
runpy.run_path('/opt/challenge/entrypoint.py', run_name='__main__')
