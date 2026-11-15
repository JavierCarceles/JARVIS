import sqlite3
con = sqlite3.connect("data/system_inventory.sqlite3")
cur = con.cursor()
print("TABLES:", [r[0] for r in cur.execute("select name from sqlite_master where type='table'").fetchall()])
print("--- machines ---")
for r in cur.execute("select * from machines").fetchall():
    print(r)
print("--- volumes ---")
for r in cur.execute("select * from volumes").fetchall():
    print(r)
print("--- application_candidates (primeras 20) ---")
rows = cur.execute("select * from application_candidates").fetchall()
print("total:", len(rows))
for r in rows[:20]:
    print(r)
