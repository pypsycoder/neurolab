#!/usr/bin/env python3
"""One bounded OpenHands candidate from a receipt-backed GigaChat spec; no merge/deploy."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
from threading import Thread
import time
from uuid import UUID, uuid4

from dotenv import dotenv_values
from neurolab.experimental_code import BASELINE, build_code_task, validate_code_asset
from neurolab.agent_event_metadata import observe_line
from neurolab.experimental_spec import DraftSpec, content_hash
from neurolab.code_diagnostics import static_diagnostics
from neurolab.code_outcomes import project_code_outcome

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'neurolab/gpt2giga-eval:v0.3.0'
CLI_SHA = '67c5cfb94e5fd4c4120eb0360b0f23337da31f64a70e8496bcf008e4caeea6af'


def command(args: list[str], *, timeout: int = 30, events: dict[str,int] | None = None) -> tuple[int, bytes]:
    """Drain output with constant memory. Never persist provider logs/transcripts."""
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    bounded = bytearray()
    def drain():
        pending = bytearray()
        while chunk := process.stdout.read1(4096):
            if len(bounded) < 16384:
                bounded.extend(chunk[:16384 - len(bounded)])
            if events is not None:
                pending.extend(chunk)
                while b'\n' in pending:
                    line, _, rest = pending.partition(b'\n'); pending[:] = rest
                    observe_line(line,events)
                    if events.get('ActionEvent',0) >= 8:
                        events['action_budget_exhausted'] = 1
                        process.kill()
                if len(pending) > 65536:
                    observe_line(pending,events); pending.clear()
        if events is not None and pending:
            observe_line(pending,events)
    reader = Thread(target=drain, daemon=True); reader.start()
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill(); process.wait(); code = 124
    reader.join(timeout=2)
    return code, bytes(bounded)


def require(args: list[str], *, timeout: int = 30) -> bytes:
    code, output = command(args, timeout=timeout)
    if code != 0:
        raise RuntimeError('sandbox runtime command failed')
    return output


def main():
    if os.environ.get('RUN_EXPERIMENTAL_CODE') != '1' or os.name != 'posix' or os.geteuid() != 0:
        raise ValueError('root Docker coordinator requires RUN_EXPERIMENTAL_CODE=1')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True)
    parser.add_argument('--repair-from', type=UUID)
    args = parser.parse_args()
    artifact_root = (ROOT/'runtime/it-research').resolve()
    spec_path = Path(args.spec).resolve()
    if spec_path.parent != artifact_root or not spec_path.name.startswith('spec-') or spec_path.stat().st_size > 40000:
        raise ValueError('spec path is outside artifact boundary')
    draft = DraftSpec.model_validate_json(spec_path.read_text(encoding='utf-8'))
    source_receipt = json.loads((artifact_root/'latest-spec-receipt.json').read_text())
    if source_receipt.get('spec_sha256') != content_hash(draft) or source_receipt.get('status') != 'draft_experimental':
        raise ValueError('spec receipt does not match')
    if spec_path.name != f"spec-{source_receipt['run_id']}.json":
        raise ValueError('spec run identity mismatch')
    previous_asset = None
    previous_receipt = None
    if args.repair_from:
        previous_path = artifact_root / f'failed-candidate-{args.repair_from}.py'
        prior_path = artifact_root / f'candidate-receipt-{args.repair_from}.json'
        if prior_path.is_symlink() or prior_path.stat().st_size > 12000:
            raise ValueError('repair receipt boundary invalid')
        previous_receipt = json.loads(prior_path.read_text())
        project_code_outcome(previous_receipt)
        if (previous_receipt.get('run_id') != str(args.repair_from) or previous_receipt.get('status') != 'candidate_failed'
                or previous_receipt.get('spec_run_id') != source_receipt['run_id']
                or previous_receipt.get('spec_sha256') != content_hash(draft)):
            raise ValueError('repair specification linkage mismatch')
        if previous_path.is_symlink() or previous_path.stat().st_size > 16000:
            raise ValueError('repair source boundary invalid')
        previous_asset = previous_path.read_bytes()
        if sha256(previous_asset).hexdigest() != previous_receipt.get('code_sha256'):
            raise ValueError('repair source hash mismatch')
    cli = ROOT/'runtime/openhands-eval/bin/openhands-1.16.0-linux-arm64'
    if sha256(cli.read_bytes()).hexdigest() != CLI_SHA:
        raise ValueError('code agent binary checksum mismatch')
    ca = ROOT/'runtime/ca/ca-certificates.crt'
    if not ca.is_file():
        raise ValueError('verified application CA is unavailable')
    if require(['docker','info','--format','{{.MemoryLimit}}']).strip() != b'true':
        raise ValueError('hard memory controller unavailable; refusing agent execution')
    # Inspect the real cgroup value, not only a requested Docker flag.
    memory = require(['docker','run','--rm','--network','none','--memory','256m','--memory-swap','256m',
        '--entrypoint','/bin/cat',IMAGE,'/sys/fs/cgroup/memory.max']).strip()
    if memory != b'268435456':
        raise ValueError('container memory limit not enforced')
    frozen = ROOT/'tests/fixtures/provenance_evaluator.py'
    frozen_hash = sha256(frozen.read_bytes()).hexdigest()
    run_id = str(uuid4()); suffix = run_id.replace('-','')[:16]
    agent_network = 'nl-code-agent-'+suffix; upstream_network = 'nl-code-upstream-'+suffix
    proxy = 'nl-code-proxy-'+suffix; agent = 'nl-code-agent-'+suffix
    evaluator = 'nl-code-eval-'+suffix
    containers = [proxy, agent, evaluator]; networks = [agent_network, upstream_network]
    started = time.monotonic()
    receipt = {'run_id':run_id,'spec_run_id':source_receipt['run_id'], 'spec_sha256':content_hash(draft),
        'boundary':'public_synthetic_experimental_only','agent':'OpenHands-CLI-1.16.0',
        'gateway':'gpt2giga-0.3.0','evaluator_sha256':frozen_hash,'status':'failed',
        'decision':'retire','production_deployed':False,'tokens_cost':'unavailable',
        'budgets':{'agent_wall_seconds':300,'agent_memory_bytes':2147483648,'agent_cpus':2,'max_tool_actions':8},
        'self_score':None,'independent_score':None,'code_executed':False,
        'repair_from':str(args.repair_from) if args.repair_from else None}
    work = Path(tempfile.mkdtemp(prefix='code-sandbox-',dir=artifact_root))
    work.chmod(0o755)
    workspace = work/'workspace'; workspace.mkdir(mode=0o755)
    experiment = workspace/'experiment'; experiment.mkdir(mode=0o700)
    target = experiment/'provenance.py'; target.write_text(BASELINE); target.chmod(0o600)
    os.chown(experiment,1000,1000); os.chown(target,1000,1000)
    try:
        security = ['--read-only','--log-driver','none','--cap-drop','ALL','--security-opt','no-new-privileges',
                    '--pids-limit','64','--cpus','2']
        def evaluate():
            code, output = command(['docker','run','--rm','--name',evaluator,'--network','none','--user','1000:1000',
                '--memory','256m','--memory-swap','256m',*security,
                '--tmpfs','/tmp:rw,noexec,nosuid,size=16m',
                '-v',f'{experiment}:/candidate:ro','-v',f'{frozen}:/frozen.py:ro',
                '--entrypoint','/usr/local/bin/python',IMAGE,'-B','/frozen.py','/candidate/provenance.py'],timeout=60)
            if code not in (0,1):
                raise RuntimeError('independent evaluator did not finish')
            result = json.loads(output)
            if result.get('evaluator_version') != 'provenance-frozen-v1' or result.get('total') != 11:
                raise ValueError('independent evaluator receipt invalid')
            return result
        baseline = evaluate()
        if baseline['passed'] != 0:
            raise ValueError('broken baseline unexpectedly passed')
        receipt['baseline'] = baseline
        if previous_asset is not None:
            target.write_bytes(previous_asset)
            validate_code_asset(experiment)
        initial_asset = target.read_bytes()
        receipt['initial_code_sha256'] = sha256(initial_asset).hexdigest()
        require(['docker','network','create','--internal',agent_network])
        require(['docker','network','create',upstream_network])
        values = dotenv_values(ROOT/'.env',interpolate=False)
        lane = os.environ.get('NEUROLAB_GIGACHAT_CODE_LANE','primary')
        if lane not in {'primary','freemium'}:
            raise ValueError('provider lane malformed')
        key_name = values.get('GIGACHAT_PRIMARY_KEY_ENV' if lane == 'primary' else 'GIGACHAT_FREEMIUM_KEY_ENV')
        if not isinstance(key_name,str) or not key_name.isidentifier() or not values.get(key_name):
            raise ValueError('provider credential lane unavailable')
        proxy_key = secrets.token_hex(32)
        scope = values.get(f'GIGACHAT_{lane.upper()}_SCOPE') or values.get('GIGACHAT_SCOPE') or 'GIGACHAT_API_PERS'
        if scope not in {'GIGACHAT_API_PERS','GIGACHAT_API_B2B','GIGACHAT_API_CORP'}:
            raise ValueError('provider scope malformed')
        model = values.get(f'GIGACHAT_{lane.upper()}_MODEL') or values.get('GIGACHAT_MODEL') or 'GigaChat-2-Pro'
        receipt['model_label'] = model
        receipt['provider_lane'] = lane
        receipt['phase'] = 'gateway_start'
        proxy_env = work/'proxy.env'
        pairs = {'GIGACHAT_CREDENTIALS':values[key_name],'GIGACHAT_SCOPE':scope,'GIGACHAT_MODEL':model,
                 'GPT2GIGA_API_KEY':proxy_key}
        if any('\n' in value or '\r' in value for value in pairs.values()):
            raise ValueError('proxy env value invalid')
        proxy_env.write_text(''.join(f'{name}={value}\n' for name,value in pairs.items())); proxy_env.chmod(0o600)
        require(['docker','run','-d','--rm','--name',proxy,'--network',upstream_network,*security,
            '--memory','512m','--memory-swap','512m','--tmpfs','/tmp:rw,noexec,nosuid,size=32m',
            '--env-file',str(proxy_env),'-e','GPT2GIGA_MODE=PROD','-e','GPT2GIGA_HOST=0.0.0.0','-e','GPT2GIGA_PORT=8090',
            '-e','GPT2GIGA_ENABLE_API_KEY_AUTH=true','-e','SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt',
            '-e','GPT2GIGA_LOG_FILENAME=/tmp/gpt2giga.log','-e','GPT2GIGA_TRAFFIC_LOG_ENABLED=false',
            '-e','GPT2GIGA_OBSERVABILITY_ENABLED=false','-e','GPT2GIGA_UI_ENABLED=false',
            '-e','GPT2GIGA_ADMIN_API_ENABLED=false','-e','GPT2GIGA_DEFAULT_MAX_TOKENS=2048',
            '-e','GIGACHAT_TIMEOUT=120',
            '-v',f'{ca}:/etc/ssl/certs/ca-certificates.crt:ro',IMAGE])
        require(['docker','network','connect','--alias','gpt2giga',agent_network,proxy])
        ready = False
        for _ in range(10):
            code,_ = command(['docker','run','--rm','--network',agent_network,*security,'--memory','128m',
                '--entrypoint','/usr/local/bin/python',IMAGE,'-c',
                'from urllib.request import urlopen; urlopen("http://gpt2giga:8090/health",timeout=2).read()'])
            if code == 0:
                ready = True; break
            time.sleep(1)
        if not ready:
            raise RuntimeError('isolated gateway not ready')
        receipt['phase'] = 'agent_run'
        events: dict[str,int] = {}
        task = build_code_task(draft)
        if previous_receipt is not None:
            feedback = {'previous_run_id':str(args.repair_from),
                'failed_cases':[item['case'] for item in previous_receipt['evaluation']['cases'] if not item['passed']],
                'static_diagnostics':previous_receipt.get('static_diagnostics',[])}
            task += '\nThe existing file is your previous failed implementation. Repair it, do not change tests.\n<INDEPENDENT_FEEDBACK>\n'+json.dumps(feedback,sort_keys=True)+'\n</INDEPENDENT_FEEDBACK>'
        code,agent_output = command(['docker','run','--rm','--name',agent,'--network',agent_network,'--user','1000:1000',
            *security,'--memory','2g','--memory-swap','2g',
            '--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--tmpfs','/home/agent:rw,nosuid,size=32m,uid=1000,gid=1000',
            '--tmpfs','/tmp/agent-cache:rw,noexec,nosuid,size=32m,uid=1000,gid=1000',
            '--tmpfs','/tmp/agent-runtime:rw,exec,nosuid,size=256m,uid=1000,gid=1000',
            '-e','HOME=/home/agent','-e','XDG_CACHE_HOME=/tmp/agent-cache','-e','TMPDIR=/tmp/agent-runtime',
            '-e','PYTHONDONTWRITEBYTECODE=1','-e','OPENHANDS_SUPPRESS_BANNER=1',
            '-e',f'LLM_API_KEY={proxy_key}','-e','LLM_BASE_URL=http://gpt2giga:8090/v1','-e',f'LLM_MODEL=openai/{model}',
            '-v',f'{cli}:/openhands:ro','-v',f'{workspace}:/workspace:ro','-v',f'{experiment}:/workspace/experiment:rw',
            '-w','/workspace/experiment','--entrypoint','/openhands',IMAGE,'--headless','--json','--always-approve',
            '--exit-without-confirmation','--override-with-envs','--task',task],timeout=300,events=events)
        receipt['agent_exit_code'] = code
        receipt['agent_event_counts'] = events
        receipt['provider_temporarily_unavailable'] = any(events.get(marker,0) for marker in ('RateLimitError','ReadTimeout','ConnectTimeout'))
        # Timeout/client termination alone does not kill a Docker container.
        command(['docker','rm','-f',agent])
        receipt['phase'] = 'independent_evaluation'
        asset, asset_hash = validate_code_asset(experiment)
        receipt['static_diagnostics'] = static_diagnostics(target)
        result = evaluate(); receipt['evaluation'] = result
        receipt['code_executed'] = True
        receipt['independent_score'] = result['passed']/result['total']
        receipt['code_sha256'] = asset_hash
        receipt['code_changed'] = asset != initial_asset
        if sha256(frozen.read_bytes()).hexdigest() != frozen_hash:
            raise ValueError('immutable evaluator changed')
        if code == 0 and receipt['code_changed'] and result['passed'] == result['total'] and not receipt['static_diagnostics']:
            destination = artifact_root/f'candidate-{run_id}.py'
            destination.write_bytes(asset); destination.chmod(0o600)
            receipt.update(status='candidate_passed',decision='harvest_parts',next_step='independent architecture integration experiment')
        else:
            destination = artifact_root/f'failed-candidate-{run_id}.py'
            destination.write_bytes(asset); destination.chmod(0o600)
            receipt.update(status='candidate_failed',decision='repair',next_step='bounded repair from failed frozen case IDs')
    finally:
        for name in containers:
            command(['docker','rm','-f',name])
        for name in networks:
            command(['docker','network','rm',name])
        # Exact generated subtree only, never a user repo, shared runtime or volume.
        if work.parent != artifact_root or not work.name.startswith('code-sandbox-'):
            raise ValueError('unsafe sandbox cleanup target')
        shutil.rmtree(work)
        receipt['wall_seconds'] = round(time.monotonic()-started,2)
        (artifact_root/f'code-receipt-{run_id}.json').write_text(json.dumps(receipt,sort_keys=True)+'\n')
        if receipt['code_executed']:
            path = artifact_root/f'candidate-receipt-{run_id}.json'
            path.write_text(json.dumps(receipt,sort_keys=True)+'\n'); path.chmod(0o600)
        print(json.dumps(receipt,sort_keys=True))
    if receipt['status'] != 'candidate_passed':
        raise SystemExit(75 if receipt.get('provider_temporarily_unavailable') else 1)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('experimental_code_failed: runtime_or_contract_failure; no raw logs retained') from None
