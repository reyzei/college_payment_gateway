import sqlite3

conn = sqlite3.connect("database.db")
cur = conn.cursor()

cur.execute("SELECT * FROM students")
rows = cur.fetchall()

print("\nstudents in DB:\n")
for row in rows:
    print(row)

cur.execute("SELECT * FROM departments")
rows = cur.fetchall()

print("\ndepartemts in DB:\n")
for row in rows:
    print(row)


conn.close()