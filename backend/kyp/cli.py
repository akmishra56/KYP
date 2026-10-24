import argparse
import json
import os
from pathlib import Path
from .repository import Repository

def main():
    parser = argparse.ArgumentParser(description='KYP local repository administration; no remote admin endpoints')
    parser.add_argument('--db', default=os.getenv('KYP_DATABASE_URL') or os.getenv('KYP_DB', 'data/kyp.sqlite3'))
    sub = parser.add_subparsers(dest='command', required=True)
    imp = sub.add_parser('import'); imp.add_argument('file')
    pending = sub.add_parser('pending')
    pending.add_argument('--state', choices=('pending','approved','rejected'), default='pending')
    pending.add_argument('--limit', type=int, default=20)
    pending.add_argument('--full', action='store_true')
    sub.add_parser('stats')
    history = sub.add_parser('history'); history.add_argument('subject', choices=('source','description')); history.add_argument('id')
    for command in ('approve-source', 'approve-description', 'reject-source', 'reject-description'):
        cmd = sub.add_parser(command); cmd.add_argument('id'); cmd.add_argument('--reviewer', required=True)
        if command.startswith('reject-'): cmd.add_argument('--reason', required=True)
    args = parser.parse_args()
    repo = Repository(args.db)
    try:
        if args.command == 'import':
            repo.import_document(json.loads(Path(args.file).read_text(encoding='utf-8-sig')))
            print('Imported as drafts. No source or description was automatically approved.')
        elif args.command == 'pending':
            if not 1 <= args.limit <= 100: raise ValueError('Limit must be between 1 and 100')
            rows = repo.pending(args.state)
            print(json.dumps({table: {'total': len(items), 'records': [row if args.full else {key: value for key, value in row.items() if key != 'payload'} for row in items[:args.limit]]} for table, items in rows.items()}, indent=2))
        elif args.command == 'stats':
            print(json.dumps(repo.stats(), indent=2))
        elif args.command == 'history':
            print(json.dumps(repo.review_history(args.subject, args.id), indent=2))
        elif args.command.startswith('reject-'):
            getattr(repo, args.command.replace('-', '_'))(args.id, args.reviewer, args.reason)
            print('Rejection recorded with reviewer and reason.')
        elif args.command == 'approve-source':
            repo.approve_source(args.id, args.reviewer)
            print('Recorded named reviewer attestation of source reuse permission. This command does not check terms automatically.')
        else:
            repo.approve_description(args.id, args.reviewer)
            print('Recorded named reviewer attestation that cited text supports this description.')
    except (ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f'Import/review rejected: {exc}\n')

if __name__ == '__main__':
    main()
