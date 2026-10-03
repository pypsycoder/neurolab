#!/usr/bin/env python3
"""Append a hash-linked independent reassessment, never change a historical code outcome."""
import argparse
import json
import os
from pathlib import Path
from uuid import UUID
from neurolab.code_cycle_gate import project_cycle_assessment, assessment_hash, validate_cycle_result


def main():
    import psycopg
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--run-id',type=UUID,required=True); args=parser.parse_args()
    path=Path(__file__).resolve().parents[1]/'runtime/it-research'/f'cycle-gate-receipt-{args.run_id}.json'
    if path.is_symlink() or path.stat().st_size>4096:
        raise ValueError('assessment receipt boundary invalid')
    receipt=project_cycle_assessment(json.loads(path.read_text()))
    if receipt['run_id']!=str(args.run_id):
        raise ValueError('assessment run mismatch')
    digest=assessment_hash(receipt); passed,_=validate_cycle_result(receipt['cycles_evaluation'])
    with psycopg.connect(os.environ['DATABASE_URL']) as connection:
        prior=connection.execute('SELECT code_sha256 FROM it_research.experimental_code_runs WHERE run_id=%s',(args.run_id,)).fetchone()
        if not prior or prior[0]!=receipt['code_sha256']:
            raise ValueError('assessment source does not match durable outcome')
        connection.execute('''INSERT INTO it_research.code_cycle_assessments
            (run_id,evaluator_sha256,code_sha256,status,passed,total,assessment_sha256,assessment)
            VALUES (%s,%s,%s,%s,%s,9,%s,%s::jsonb) ON CONFLICT (run_id,evaluator_sha256) DO NOTHING''',
            (args.run_id,receipt['cycles_evaluator_sha256'],receipt['code_sha256'],receipt['status'],passed,digest,json.dumps(receipt,sort_keys=True)))
        stored=connection.execute('SELECT assessment_sha256 FROM it_research.code_cycle_assessments WHERE run_id=%s AND evaluator_sha256=%s',(args.run_id,receipt['cycles_evaluator_sha256'])).fetchone()
        if not stored or stored[0]!=digest:
            raise ValueError('immutable assessment conflict')
    print(json.dumps({'run_id':str(args.run_id),'status':receipt['status'],'passed':passed,'total':9,'persisted':True,'assessment_sha256':digest},sort_keys=True))


if __name__=='__main__':
    try:
        main()
    except Exception:
        raise SystemExit('cycle_assessment_failed: integrity_or_storage_failure') from None
