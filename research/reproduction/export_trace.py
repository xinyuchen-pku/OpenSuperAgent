"""Export a completed immutable journal with record fields separate from payload fields.

Frozen source025's flattened JSON can overwrite record kind with Event.kind.
The original SQLite and flattened export remain unchanged; this is a derived view.
"""
from pathlib import Path
import argparse, hashlib, json, sqlite3


def export(database,output):
    database=Path(database).resolve();output=Path(output)
    assert not output.exists()
    assert not Path(str(database)+'-wal').exists(),'Use a completed, checkpointed journal'
    before=hashlib.sha256(database.read_bytes()).hexdigest()
    connection=sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        records=[{'seq':seq,'at':at,'kind':kind,'payload':json.loads(payload)}
                 for seq,at,kind,payload in connection.execute('SELECT seq,at,kind,payload FROM trace ORDER BY seq')]
    finally:connection.close()
    output.write_text(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n'for r in records),encoding='utf-8')
    assert hashlib.sha256(database.read_bytes()).hexdigest()==before
    return {'records':len(records),'source_database_sha256':before,'source_modified':False,
            'payload_fields_nested':True,'actual_api_calls':0}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(export(a.database,a.output)))
