import sqlite3
conn = sqlite3.connect('data/system_inventory.sqlite3')
conn.row_factory = sqlite3.Row
cur = conn.execute("SELECT name, absolute_path, launch_type, source FROM application_candidates WHERE lower(name) LIKE '%discord%'")
rows = cur.fetchall()
print(f"Candidatos Discord encontrados: {len(rows)}")
for r in rows:
    d = dict(r)
    print(f"  nombre={d['name']!r} | ruta={d['absolute_path']!r} | tipo={d['launch_type']!r} | fuente={d['source']!r}")
conn.close()
