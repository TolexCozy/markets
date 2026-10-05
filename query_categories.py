import sqlite3

conn = sqlite3.connect('db.sqlite3')
cur = conn.cursor()
cur.execute('SELECT DISTINCT category FROM events_product')
rows = cur.fetchall()
print(rows)
conn.close()
