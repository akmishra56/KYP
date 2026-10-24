"""Copy a local SQLite repo into PostgreSQL without dropping or overwriting data."""
import argparse
import os
from pathlib import Path
from .repository import Repository

def migrate(sqlite_path,postgres_url):
    if not Path(sqlite_path).is_file() or not postgres_url.startswith(('postgresql://','postgres://')):
        raise ValueError('Provide an existing SQLite file and PostgreSQL URL')
    source=Repository(sqlite_path)
    destination=Repository(postgres_url)
    if source.postgres or not destination.postgres:
        raise ValueError('Migration requires SQLite source and PostgreSQL destination')
    counts={}
    identities={'ingredients':('id',),'aliases':('ingredient_id','alias'),'sources':('id',),'descriptions':('id',),'review_events':('id',),'ingredient_contexts':('ingredient_id','context')}
    immutable={'ingredients':('name',),'aliases':(),'sources':('payload',),'descriptions':('ingredient_id','payload'),'review_events':('subject_type','subject_id','decision','reviewer','reason','created_at'),'ingredient_contexts':()}
    with source.connection() as old, destination.connection() as new:
        for table in ('ingredients','aliases','sources','descriptions','review_events','ingredient_contexts'):
            rows=old.execute('SELECT * FROM '+table).fetchall()
            for row in rows:
                data=dict(row);keys=list(data)
                where=' AND '.join(k+'=?' for k in identities[table])
                existing=new.execute('SELECT * FROM '+table+' WHERE '+where,tuple(data[k] for k in identities[table])).fetchone()
                if existing:
                    if any(existing[k]!=data[k] for k in immutable[table]):
                        raise ValueError('Conflicting immutable record in '+table+'; destination was not overwritten')
                else:
                    new.execute('INSERT INTO '+table+'('+','.join(keys)+') VALUES('+','.join('?' for _ in keys)+')',tuple(data[k] for k in keys))
            counts[table]=len(rows)
    return counts

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sqlite',default='data/kyp.sqlite3')
    parser.add_argument('--postgres',default=os.getenv('KYP_DATABASE_URL'))
    args=parser.parse_args()
    if not args.postgres:parser.error('Set KYP_DATABASE_URL or provide --postgres')
    print('Migration completed; existing destination reviews preserved:',migrate(args.sqlite,args.postgres))

if __name__=='__main__':main()
