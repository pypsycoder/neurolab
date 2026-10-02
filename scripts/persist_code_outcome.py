#!/usr/bin/env python3
"""Append final measured metadata; accepted code becomes a candidate asset, never promoted."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import UUID

from neurolab.code_outcomes import project_code_outcome, outcome_hash


def main():
    import psycopg
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True,type=UUID)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]/'runtime/it-research'
    path=root/f'candidate-receipt-{args.run_id}.json'
    if path.is_symlink() or path.stat().st_size>12000:
        raise ValueError('outcome receipt boundary invalid')
    outcome=project_code_outcome(json.loads(path.read_text()))
    if outcome['run_id']!=str(args.run_id):
        raise ValueError('outcome run identity mismatch')
    prefix='candidate' if outcome['status']=='candidate_passed' else 'failed-candidate'
    source=root/f'{prefix}-{args.run_id}.py'
    if source.is_file():
        if source.is_symlink() or source.stat().st_size>16000 or sha256(source.read_bytes()).hexdigest()!=outcome['code_sha256']:
            raise ValueError('outcome asset integrity invalid')
        outcome['artifact_ref']=source.name
    elif outcome['status']=='candidate_passed':
        raise ValueError('accepted asset missing')
    else:
        outcome['artifact_ref']=None
    with psycopg.connect(os.environ['DATABASE_URL']) as connection:
        spec=connection.execute('SELECT spec_sha256 FROM it_research.experimental_specs WHERE run_id=%s',(outcome['spec_run_id'],)).fetchone()
        if not spec or spec[0]!=outcome['spec_sha256']:
            raise ValueError('outcome specification linkage mismatch')
        asset_id=None
        if outcome['status']=='candidate_passed':
            connection.execute('''INSERT INTO it_research.solution_assets (id,asset_kind,label,content_sha256,state)
                VALUES (%s,'code_component','Synthetic provenance DAG',%s,'candidate') ON CONFLICT (asset_kind,content_sha256) DO NOTHING''',(outcome['run_id'],outcome['code_sha256']))
            asset_id=connection.execute("SELECT id FROM it_research.solution_assets WHERE asset_kind='code_component' AND content_sha256=%s",(outcome['code_sha256'],)).fetchone()[0]
        digest=outcome_hash(outcome)
        connection.execute('''INSERT INTO it_research.experimental_code_runs (run_id,spec_run_id,asset_id,status,code_sha256,independent_score,outcome_sha256,outcome)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT (run_id) DO NOTHING''',
            (outcome['run_id'],outcome['spec_run_id'],asset_id,outcome['status'],outcome['code_sha256'],outcome['independent_score'],digest,json.dumps(outcome,sort_keys=True)))
        stored=connection.execute('SELECT outcome_sha256 FROM it_research.experimental_code_runs WHERE run_id=%s',(outcome['run_id'],)).fetchone()[0]
        if stored!=digest:
            raise ValueError('immutable outcome conflict')
    print(json.dumps({'run_id':outcome['run_id'],'status':outcome['status'],'outcome_sha256':digest,'asset_state':'candidate' if asset_id else None,'persisted':True},sort_keys=True))


if __name__=='__main__':
    try:
        main()
    except Exception:
        raise SystemExit('code_outcome_failed: integrity_or_storage_failure') from None
