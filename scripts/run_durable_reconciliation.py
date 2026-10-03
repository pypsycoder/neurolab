#!/usr/bin/env python3
"""Persist/resume existing synthetic receipts. This is NOT the paid research scheduler."""
import argparse
import json
import os
from uuid import UUID
from neurolab.durable_reconciliation import build_reconciliation_graph, run_or_resume
from neurolab.experimental_spec import DraftSpec, content_hash
from neurolab.code_outcomes import outcome_hash


def main():
    import psycopg
    from psycopg.rows import dict_row
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workflow-id',required=True,type=UUID)
    parser.add_argument('--spec-run-id',required=True,type=UUID)
    parser.add_argument('--code-run-id',required=True,type=UUID)
    parser.add_argument('--stop-after-spec',action='store_true')
    parser.add_argument('--cancel',action='store_true')
    parser.add_argument('--setup',action='store_true',help='explicit first-use official checkpoint schema setup')
    args=parser.parse_args()
    if args.cancel and args.stop_after_spec:
        raise ValueError('incompatible workflow actions')
    # Serializer only permits primitive state; no pickle or arbitrary imports.
    serde=JsonPlusSerializer(pickle_fallback=False,allowed_json_modules=[],allowed_msgpack_modules=[])
    with psycopg.connect(os.environ['DATABASE_URL'],autocommit=True,row_factory=dict_row,
        options='-c search_path=it_research,public -c statement_timeout=30000') as connection:
        connection.execute('SELECT pg_advisory_lock(hashtextextended(%s,0))',('neurolab-reconcile-v1:'+str(args.workflow_id),))
        saver=PostgresSaver(connection,serde=serde)
        if args.setup:
            saver.setup()
        def load_spec(run_id):
            row=connection.execute('SELECT spec,spec_sha256 FROM it_research.experimental_specs WHERE run_id=%s',(run_id,)).fetchone()
            if not row or content_hash(DraftSpec.model_validate(row['spec']))!=row['spec_sha256']:
                raise ValueError('spec integrity failure')
            return {'spec_sha256':row['spec_sha256']}
        def load_outcome(run_id):
            row=connection.execute('SELECT outcome,outcome_sha256 FROM it_research.experimental_code_runs WHERE run_id=%s',(run_id,)).fetchone()
            if not row or outcome_hash(row['outcome'])!=row['outcome_sha256'] or row['outcome']['run_id']!=run_id:
                raise ValueError('outcome integrity failure')
            return dict(row['outcome'],outcome_sha256=row['outcome_sha256'])
        graph=build_reconciliation_graph(saver,load_spec,load_outcome,stop_after_spec=args.stop_after_spec)
        result=run_or_resume(graph,str(args.workflow_id),str(args.spec_run_id),str(args.code_run_id),cancel=args.cancel)
        print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    try:
        main()
    except Exception:
        raise SystemExit('durable_reconciliation_failed: integrity_or_storage_failure') from None
