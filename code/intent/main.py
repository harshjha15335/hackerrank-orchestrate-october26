"""Run offline M3 intent classification without creating deletion output.csv."""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intent.classifier import IntentClassifier


def main(argv=None):
    root=Path(__file__).resolve().parents[2]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample',action='store_true')
    parser.add_argument('--route-log',type=Path,help='new local file outside repository for exact ambiguous texts')
    args=parser.parse_args(argv)
    if args.route_log and args.route_log.resolve().is_relative_to(root):
        parser.error('--route-log must be outside the repository')
    name='sample_deletion_requests.csv' if args.sample else 'deletion_requests.csv'
    with (root/'dataset'/name).open(newline='',encoding='utf-8') as stream:
        rows=list(csv.DictReader(stream))
    classifier=IntentClassifier()
    decisions=[];routed=[]
    for row in rows:
        result=classifier.classify(row['request_text'])
        decisions.append({'case_id':row['case_id'],'intent':result.intent,'route':result.route,
                          'degraded':result.degraded,'reason':result.reason})
        if result.route=='offline_fallback':
            routed.append({'case_id':row['case_id'],'request_text':row['request_text']})
    if args.route_log:
        with args.route_log.open('x',encoding='utf-8') as stream:
            json.dump(routed,stream,ensure_ascii=False,sort_keys=True,indent=2)
            stream.write('\n')
    counts=Counter(d['intent'] for d in decisions)
    print(json.dumps({'count':len(rows),'distribution':dict(sorted(counts.items())),
                      'routed_count':len(routed),'model_calls':0,
                      'decisions':decisions},ensure_ascii=False,sort_keys=True))


if __name__=='__main__':
    main()
