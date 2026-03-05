import sqlite3

conn = sqlite3.connect("backend/sams.db")
cur = conn.cursor()

print("\n=== TABLES IN DATABASE ===")
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
print(cur.fetchall())

print("\n=== STUDENTS TABLE STRUCTURE ===")
cur.execute("PRAGMA table_info(students);")
print(cur.fetchall())

print("\n=== FIRST 10 STUDENTS ===")
try:
    cur.execute("SELECT * FROM students LIMIT 10;")
    print(cur.fetchall())
except Exception as e:
    print("Error reading students table:", e)

conn.close()
