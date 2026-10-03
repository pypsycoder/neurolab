#!/usr/bin/env python3
"""Independent network-none shadow assessment of a stored code asset; no model calls."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import UUID
from neurolab.code_cycle_gate import validate_cycle_result
from run_experimental_code import ROOT, IMAGE, command, require, publish_artifact


def main():
    if os.name!='posix' or os.geteuid()!=0:
        raise ValueError('root Docker verifier required')
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--run-id',type=UUID,required=True); args=parser.parse_args()
    root=ROOT/'runtime/it-research'
    prior_path=root/f'candidate-receipt-{args.run_id}.json'
    if prior_path.is_symlink() or prior_path.stat().st_size>12000:
        raise ValueError('prior receipt boundary invalid')
    prior=json.loads(prior_path.read_text())
    prefix='candidate' if prior['status']=='candidate_passed' else 'failed-candidate'
    source=root/f'{prefix}-{args.run_id}.py'
    if prior['run_id']!=str(args.run_id) or source.is_symlink() or source.stat().st_size>16000 or sha256(source.read_bytes()).hexdigest()!=prior['code_sha256']:
        raise ValueError('source integrity mismatch')
    fixture=ROOT/'tests/fixtures/provenance_cycle_evaluator.py'; digest=sha256(fixture.read_bytes()).hexdigest()
    if require(['docker','run','--rm','--network','none','--memory','256m','--memory-swap','256m','--entrypoint','/bin/cat',IMAGE,'/sys/fs/cgroup/memory.max']).strip()!=b'268435456':
        raise ValueError('actual memory limit not enforced')
    name='nl-cycle-check-'+str(args.run_id).replace('-','')[:16]
    try:
        code, output=command(['docker','run','--rm','--name',name,'--network','none','--user','1000:1000',
            '--read-only','--log-driver','none','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','32','--cpus','1',
            '--memory','256m','--memory-swap','256m','--tmpfs','/tmp:rw,noexec,nosuid,size=16m',
            '-v',f'{source}:/candidate.py:ro','-v',f'{fixture}:/cycles.py:ro','--entrypoint','/usr/local/bin/python',IMAGE,'-B','/cycles.py','/candidate.py'],timeout=60)
        if code not in {0,1}:
            raise ValueError('cycle evaluation incomplete')
        result=json.loads(output); passed,_=validate_cycle_result(result)
        if sha256(fixture.read_bytes()).hexdigest()!=digest:
            raise ValueError('cycle fixture changed')
        receipt={'run_id':str(args.run_id),'code_sha256':prior['code_sha256'],'cycles_evaluator_sha256':digest,
                 'cycles_evaluation':result,'status':'passed' if passed==9 else 'failed','new_model_calls':0,
                 'historical_outcome_modified':False,'production_deployed':False}
        publish_artifact(root/f'cycle-gate-receipt-{args.run_id}.json',(json.dumps(receipt,sort_keys=True)+'\n').encode())
        print(json.dumps(receipt,sort_keys=True))
        if passed!=9:
            raise SystemExit(1)
    finally:
        command(['docker','rm','-f',name])


if __name__=='__main__':
    try:
        main()
    except Exception:
        raise SystemExit('cycle_gate_failed: integrity_or_runtime_failure') from None
