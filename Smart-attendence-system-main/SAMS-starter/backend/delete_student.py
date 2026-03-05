import os
import glob
from sqlalchemy import create_engine, text

# --- Config ---
DB_PATH = "sams.db"  
DATA_DIR = "data"
EMBED_DIR = os.path.join("data", "embeddings")

def delete_student(student_id):
    print(f"--- Deleting Student: {student_id} ---")
    
    # 1. Clean up Database
    if os.path.exists(DB_PATH):
        try:
            engine = create_engine(f"sqlite:///{DB_PATH}")
            with engine.connect() as conn:
                # Delete Attendance records
                conn.execute(text("DELETE FROM attendance WHERE student_id = :sid"), {"sid": student_id})
                # Delete Enrollments
                conn.execute(text("DELETE FROM enrollments WHERE student_id = :sid"), {"sid": student_id})
                # Delete Student record
                conn.execute(text("DELETE FROM students WHERE student_id = :sid"), {"sid": student_id})
                conn.commit()
            print(" Database records removed.")
        except Exception as e:
            print(f" Database error: {e}")
    else:
        print("  Database file not found.")

    # 2. Delete Images (data/USN_*.jpg)
    # This finds any file in 'data' that starts with the student_id
    images = glob.glob(os.path.join(DATA_DIR, f"{student_id}*"))
    for img in images:
        try:
            os.remove(img)
            print(f" Deleted image: {img}")
        except OSError as e:
            print(f" Error deleting {img}: {e}")

    # 3. Delete Embedding (data/embeddings/USN.npy)
    embed_path = os.path.join(EMBED_DIR, f"{student_id}.npy")
    if os.path.exists(embed_path):
        try:
            os.remove(embed_path)
            print(f" Deleted embedding: {embed_path}")
        except OSError as e:
            print(f" Error deleting embedding: {e}")
    else:
        print("  No embedding file found.")

    print("\nDone! Please restart your backend server if it is running.")

if __name__ == "__main__":
    sid = input("Enter Student ID to delete (e.g., u020): ").strip()
    if sid:
        delete_student(sid)
    else:
        print("Operation cancelled.")