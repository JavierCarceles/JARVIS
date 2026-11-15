import sqlite3, os
db = 'data/error_recovery.db'
if os.path.exists(db):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    print('TABLES:', cur.fetchall())
    try:
        cur.execute('PRAGMA table_info(error_logs)')
        print('SCHEMA error_logs:', cur.fetchall())
        cur.execute("SELECT error_type, severity, component, error_message, COUNT(*) as c FROM error_logs GROUP BY error_type, severity, component, error_message ORDER BY c DESC LIMIT 20")
        rows = cur.fetchall()
        print('GROUPED ERRORS:')
        for r in rows:
            print(r)
    except Exception as e:
        print('error_logs error:', e)
    conn.close()
else:
    print('DB does not exist')
