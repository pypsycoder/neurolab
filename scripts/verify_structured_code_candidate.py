#!/usr/bin/env python3
"""Same frozen independent evaluator as OpenHands, no provider or host code execution."""
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from uuid import UUID

from neurolab.experimental_code import BASELINE, validate_code_asset
from run_experimental_code import command, require, IMAGE


def main():
    if os.name!='posix' or os.geteuid()!=0:
        raise ValueError('root Docker evaluator required')
    root=Path(__file__).resolve().parents[1]; artifacts=root/'runtime/it-research'
    receipt=json.loads((artifacts/'latest-candidate-receipt.json').read_text())
    run_id=str(UUID(receipt['run_id']))
    if receipt['status']!='pending_independent_evaluation' or receipt['boundary']!='public_synthetic_experimental_only':
        raise ValueError('candidate receipt state invalid')
    source=artifacts/f'pending-candidate-{run_id}.py'
    if source.is_symlink() or source.stat().st_size>16000 or sha256(source.read_bytes()).hexdigest()!=receipt['code_sha256']:
        raise ValueError('candidate integrity invalid')
    if require(['docker','info','--format','{{.MemoryLimit}}']).strip()!=b'true':
        raise ValueError('memory controller required')
    if require(['docker','run','--rm','--network','none','--memory','256m','--memory-swap','256m',
                '--entrypoint','/bin/cat',IMAGE,'/sys/fs/cgroup/memory.max']).strip()!=b'268435456':
        raise ValueError('actual evaluation memory limit not enforced')
    frozen=root/'tests/fixtures/provenance_evaluator.py'
    receipt['evaluator_sha256']=sha256(frozen.read_bytes()).hexdigest()
    container='nl-sdk-eval-'+run_id.replace('-','')[:16]
    work=Path(tempfile.mkdtemp(prefix='candidate-eval-',dir=artifacts)); work.chmod(0o755)
    target=work/'provenance.py'
    try:
        def evaluate(code):
            target.write_bytes(code); target.chmod(0o644)
            status,output=command(['docker','run','--rm','--name',container,'--network','none','--user','1000:1000',
                '--read-only','--log-driver','none','--cap-drop','ALL','--security-opt','no-new-privileges',
                '--pids-limit','32','--cpus','1','--memory','256m','--memory-swap','256m',
                '--tmpfs','/tmp:rw,noexec,nosuid,size=16m','-v',f'{target}:/candidate.py:ro',
                '-v',f'{frozen}:/frozen.py:ro','--entrypoint','/usr/local/bin/python',
                IMAGE,'-B','/frozen.py','/candidate.py'],timeout=60)
            if status not in {0,1}:
                raise ValueError('independent evaluation did not finish')
            result=json.loads(output)
            if result['total']!=11 or result['evaluator_version']!='provenance-frozen-v1':
                raise ValueError('independent evaluation receipt invalid')
            return result
        receipt['baseline']=evaluate(BASELINE.encode())
        if receipt['baseline']['passed']!=0:
            raise ValueError('baseline gate failed')
        target.write_bytes(source.read_bytes())
        code,digest=validate_code_asset(work)
        receipt['evaluation']=evaluate(code)
        receipt['code_executed']=True
        receipt['independent_score']=receipt['evaluation']['passed']/11
        if sha256(frozen.read_bytes()).hexdigest()!=receipt['evaluator_sha256']:
            raise ValueError('frozen evaluator changed')
        passed=receipt['evaluation']['passed']==11
        receipt.update(status='candidate_passed' if passed else 'candidate_failed',decision='harvest_parts' if passed else 'repair',production_deployed=False,
            next_step='independent integration experiment' if passed else 'bounded repair from failed case IDs')
        if passed:
            source.replace(artifacts/f'candidate-{run_id}.py')
        else:
            source.unlink()
        (artifacts/f'candidate-receipt-{run_id}.json').write_text(json.dumps(receipt,sort_keys=True)+'\n')
        (artifacts/'latest-candidate-receipt.json').write_text(json.dumps(receipt,sort_keys=True)+'\n')
        print(json.dumps(receipt,sort_keys=True))
        if not passed:
            raise SystemExit(1)
    finally:
        command(['docker','rm','-f',container])
        if work.parent!=artifacts or not work.name.startswith('candidate-eval-'):
            raise ValueError('unsafe cleanup target')
        shutil.rmtree(work)


if __name__=='__main__':
    try:
        main()
    except Exception:
        raise SystemExit('candidate_evaluation_failed: runtime_or_contract_failure') from None
