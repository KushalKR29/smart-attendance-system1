import cv2
import threading
import time
import os
import io
import json
import queue
import datetime
from typing import List, Dict, Any, Optional

from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS
from werkzeug.utils import secure_filename

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session

from PIL import Image

# --- Flask app ---
app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return send_from_directory("../frontend", "login.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("../frontend", path)

# Try to import recognition pipeline
try:
    from recognition import recognize_frame, enroll_image, enroll_images
    HAS_RECOGNITION = True
except Exception:
    recognize_frame = None
    enroll_image = None
    enroll_images = None
    HAS_RECOGNITION = False
    print("WARNING: recognition.py not available or incomplete. Recognition will return empty matches.")

# --- Config ---
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(BASE_DIR, "sams.db")
SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"

DEFAULT_TERM_SESSIONS = 30  


# --- SQLAlchemy setup ---
Base = declarative_base()

engine = create_engine(
    SQLALCHEMY_DATABASE_URI,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False
)

# Flask app
app = Flask(__name__)
CORS(app)
class Period(Base):
    __tablename__ = "periods"

    id = Column(Integer, primary_key=True, index=True)
    class_code = Column(String, ForeignKey("classes.code"), nullable=False)

    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)

    weekday = Column(String, nullable=True)
    room = Column(String, nullable=True)

    active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
# --- Models ---
class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    meta = Column(Text, nullable=True)

class ClassRoom(Base):
    __tablename__ = "classes"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    teacher = Column(String, nullable=True)  # use username/teacher_id

class Enrollment(Base):
    __tablename__ = "enrollments"
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(String, ForeignKey("students.student_id"), nullable=False, index=True)
    class_code = Column(String, ForeignKey("classes.code"), nullable=False, index=True)


    __tablename__ = "periods"
    id = Column(Integer, primary_key=True, index=True)
    class_code = Column(String, ForeignKey("classes.code"), nullable=False)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    weekday = Column(String, nullable=True)  # "Mon", "Tue", ...
    active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    room = Column(String, nullable=True) 
    
    active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
class Attendance(Base):
    __tablename__ = "attendance"
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(String, index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    source = Column(String, default="camera")
    note = Column(Text, nullable=True)
    class_code = Column(String, nullable=True)
    period_id = Column(Integer, nullable=True)

Base.metadata.create_all(bind=engine)

# --- SSE clients ---
clients: List[queue.Queue] = []

def broadcast_event(data: Dict[str, Any]):
    payload = json.dumps(data)
    for q in list(clients):
        try:
            q.put_nowait(payload)
        except Exception:
            pass

# --- Helpers ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_all_students() -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        rows = db.query(Student).order_by(Student.student_id).all()
        return [{"student_id": r.student_id, "name": r.name or ""} for r in rows]
    finally:
        db.close()

def ensure_student(student_id: str, name: Optional[str] = None):
    db = SessionLocal()
    try:
        s = db.query(Student).filter_by(student_id=student_id).first()
        if not s:
            s = Student(student_id=student_id, name=name or "")
            db.add(s)
            db.commit()
        else:
            changed = False
            if name and (not s.name or s.name != name):
                s.name = name
                changed = True
            if changed:
                db.commit()
    finally:
        db.close()

def ensure_class(code: str, name: Optional[str] = None, teacher: Optional[str] = None):
    db = SessionLocal()
    try:
        c = db.query(ClassRoom).filter_by(code=code).first()
        if not c:
            c = ClassRoom(code=code, name=name or "", teacher=teacher or "")
            db.add(c)
            db.commit()
        else:
            changed = False
            if name and c.name != name:
                c.name = name
                changed = True
            if teacher and c.teacher != teacher:
                c.teacher = teacher
                changed = True
            if changed:
                db.commit()
    finally:
        db.close()

def add_attendance(student_id: str,
                   timestamp: Optional[datetime.datetime] = None,
                   source: str = "camera",
                   note: Optional[str] = None,
                   class_code: Optional[str] = None,
                   period_id: Optional[int] = None):
    db = SessionLocal()
    try:
        ts = timestamp or datetime.datetime.utcnow()
        rec = Attendance(
            student_id=student_id,
            timestamp=ts,
            source=source,
            note=note,
            class_code=class_code,
            period_id=period_id,
        )
        db.add(rec)
        db.commit()
        return True
    finally:
        db.close()

def get_attendance_history(student_id: str, limit: int = 500) -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        rows = (
            db.query(Attendance)
            .filter_by(student_id=student_id)
            .order_by(Attendance.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "timestamp": r.timestamp.isoformat(),
                "source": r.source,
                "note": r.note,
                "class_code": r.class_code,
                "period_id": r.period_id,
            }
            for r in rows
        ]
    finally:
        db.close()

def compute_summary(class_filter: Optional[str] = None, from_iso: Optional[str] = None, to_iso: Optional[str] = None):
    """
    Returns:
      { summary: [ { student_id, name, present_count, total_classes, percentage, last_seen } ... ],
        overall: <percentage avg>,
        total_classes: <int - classes for class_filter> }
    Uses Attendance rows for present_count and Periods table to estimate total classes for given class_filter.
    """
    db = SessionLocal()
    try:
        
        total_classes = 0
        if class_filter:
            try:
                
                total_classes = db.execute(
                    "SELECT COUNT(*) FROM periods WHERE class_code = :cc", {"cc": class_filter}
                ).scalar() or 0
            except Exception:
                total_classes = 0

        students = db.query(Student).order_by(Student.student_id).all()
        summary = []
        for s in students:
            # filter by class if student meta has class_code and it doesn't match, skip
            skip = False
            if class_filter:
                try:
                    meta = json.loads(s.meta) if s.meta else {}
                    sc = meta.get("class_code")
                    if sc and sc != class_filter:
                        skip = True
                except Exception:
                    pass
            if skip:
                continue

            q = db.query(Attendance).filter(Attendance.student_id == s.student_id)
            if from_iso:
                try:
                    dt_from = datetime.datetime.fromisoformat(from_iso)
                    q = q.filter(Attendance.timestamp >= dt_from)
                except Exception:
                    pass
            if to_iso:
                try:
                    dt_to = datetime.datetime.fromisoformat(to_iso)
                    q = q.filter(Attendance.timestamp <= dt_to)
                except Exception:
                    pass
            present_count = q.count()
            last = q.order_by(Attendance.timestamp.desc()).first()
            last_seen = last.timestamp.isoformat() if last else None

            # safetly compute percentage
            pct = 0
            if total_classes > 0:
                pct = min(100, round((present_count / total_classes) * 100))
            else:
                # fallback to DEFAULT_TERM_SESSIONS (older behavior)
                pct = min(100, round((present_count / DEFAULT_TERM_SESSIONS) * 100)) if DEFAULT_TERM_SESSIONS > 0 else 0

            summary.append({
                "student_id": s.student_id,
                "name": s.name or "",
                "present_count": present_count,
                "total_classes": total_classes,
                "percentage": pct,
                "last_seen": last_seen
            })

        overall = round(sum(item["percentage"] for item in summary) / len(summary), 2) if summary else 0
        return {"summary": summary, "overall": overall, "total_classes": total_classes}
    finally:
        db.close()


def compute_class_summary(class_code: str,
                          from_iso: Optional[str] = None,
                          to_iso: Optional[str] = None) -> Dict[str, Any]:
    """
    NEW summary per class_code:
    - total_classes = distinct dates for that class_code
    - per student: attended count and percentage.
    Uses Enrollment if available, otherwise falls back to any student with attendance in that class.
    """
    db: Session = SessionLocal()
    try:
        # base query for attendance in this class
        q = db.query(Attendance).filter(Attendance.class_code == class_code)
        if from_iso:
            try:
                dt_from = datetime.datetime.fromisoformat(from_iso)
                q = q.filter(Attendance.timestamp >= dt_from)
            except Exception:
                pass
        if to_iso:
            try:
                dt_to = datetime.datetime.fromisoformat(to_iso)
                q = q.filter(Attendance.timestamp <= dt_to)
            except Exception:
                pass

        rows = q.all()
        # determine total classes held (distinct dates)
        dates = {r.timestamp.date() for r in rows}
        total_classes = len(dates)

        # determine student list
        enrollments = db.query(Enrollment).filter(Enrollment.class_code == class_code).all()
        if enrollments:
            student_ids = sorted({e.student_id for e in enrollments})
        else:
            student_ids = sorted({r.student_id for r in rows})

        # name lookup
        students_map = {
            s.student_id: (s.name or "")
            for s in db.query(Student).filter(Student.student_id.in_(student_ids)).all()
        }

        # attendance count per student
        result = []
        for sid in student_ids:
            attended = len([r for r in rows if r.student_id == sid])
            if total_classes > 0:
                percentage = round((attended / total_classes) * 100, 2)
            else:
                percentage = 0.0
            result.append({
                "student_id": sid,
                "name": students_map.get(sid, ""),
                "attended": attended,
                "total": total_classes,
                "percentage": percentage,
            })

        return {
            "class_code": class_code,
            "total_classes": total_classes,
            "students": result,
        }
    finally:
        db.close()

def create_period(class_code: str,
                  start_time: Optional[datetime.datetime] = None,
                  end_time: Optional[datetime.datetime] = None,
                  weekday: Optional[str] = None) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        p = Period(
            class_code=class_code,
            start_time=start_time,
            end_time=end_time,
            weekday=weekday,
            active=False,
        )
        db.add(p)
        db.commit()
        return {"id": p.id, "class_code": p.class_code}
    finally:
        db.close()

def set_period_active(period_id: int, active: bool) -> bool:
    db = SessionLocal()
    try:
        p = db.query(Period).filter_by(id=period_id).first()
        if not p:
            return False
        p.active = active
        db.commit()
        return True
    finally:
        db.close()

def mark_attendance_once(session: Session,
                         student_id: str,
                         class_code: Optional[str],
                         period_id: Optional[int],
                         source: str = "camera") -> bool:
    """
    Mark attendance if not already present for (student_id, period_id).
    Returns True if recorded, False if duplicate.
    """
    if period_id is not None:
        exists = (
            session.query(Attendance)
            .filter_by(student_id=student_id, period_id=period_id)
            .first()
        )
        if exists:
            return False
    rec = Attendance(
        student_id=student_id,
        timestamp=datetime.datetime.utcnow(),
        source=source,
        class_code=class_code,
        period_id=period_id,
    )
    session.add(rec)
    session.commit()
    broadcast_event(
        {
            "type": "attendance_marked",
            "student_id": student_id,
            "period_id": period_id,
            "class_code": class_code,
            "timestamp": rec.timestamp.isoformat(),
        }
    )
    return True

def period_to_dict(p: Period, cls: Optional[ClassRoom] = None) -> Dict[str, Any]:
    return {
        "id": p.id,
        "class_code": p.class_code,
        "weekday": p.weekday,
        "start_time": p.start_time.isoformat() if p.start_time else None,
        "end_time": p.end_time.isoformat() if p.end_time else None,
        "active": bool(p.active),
        "class_name": (cls.name if cls else None),
        "teacher": (cls.teacher if cls else None),
    }

# --- Routes ---

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": datetime.datetime.utcnow().isoformat()})

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(force=True, silent=True) or {}
    username = data.get("username") or request.form.get("username")
    password = data.get("password") or request.form.get("password")
    if not username or not password:
        return jsonify({"error": "username/password required"}), 400
    if (username == "teacher1" and password == "pass") or (username == "admin" and password == "admin"):
        token = "mock-token-" + username
        return jsonify({"token": token, "role": "teacher", "name": username, "teacher_id": username})
    return jsonify({"error": "invalid credentials"}), 401

# --- Students & attendance history ---

@app.route("/api/students", methods=["GET"])
def api_students():
    students = get_all_students()
    return jsonify({"students": students})

@app.route("/api/attendance/<string:student_id>", methods=["GET"])
def api_attendance(student_id):
    history = get_attendance_history(student_id)
    return jsonify({"student_id": student_id, "history": history})

@app.route("/api/attendance/summary", methods=["GET"])
def api_attendance_summary():
    class_filter = request.args.get("class")
    from_iso = request.args.get("from")
    to_iso = request.args.get("to")
    data = compute_summary(class_filter, from_iso, to_iso)
    return jsonify(data)

@app.route("/api/attendance/class_summary", methods=["GET"])
def api_attendance_class_summary():
    """
    New endpoint:
      GET /api/attendance/class_summary?class_code=CS101
      optional: &from=ISO &to=ISO
    """
    class_code = request.args.get("class_code")
    if not class_code:
        return jsonify({"error": "class_code query parameter required"}), 400
    from_iso = request.args.get("from")
    to_iso = request.args.get("to")
    data = compute_class_summary(class_code, from_iso, to_iso)
    return jsonify(data)

@app.route("/api/attendance/mark", methods=["POST"])
def api_mark_attendance():
    """
    Manual or camera marking.
    Accepts JSON:
      { student_id, status: "present"|"absent", timestamp?, source?, name?, class_code?, period_id? }
    Uses mark_attendance_once() to avoid duplicates and broadcast SSE updates.
    Returns { ok, student_id, recorded, class_summary?: {...} }
    """
    data = request.get_json(force=True, silent=True) or {}
    sid = data.get("student_id")
    status = data.get("status", "present")
    ts = data.get("timestamp")
    source = data.get("source", "manual")
    note = data.get("note")
    name = data.get("name")
    class_code = data.get("class_code")
    period_id = data.get("period_id")

    if not sid:
        return jsonify({"error": "student_id required"}), 400

    try:
        dt = datetime.datetime.fromisoformat(ts) if ts else None
    except Exception:
        dt = None

    db = SessionLocal()
    try:
        # create or update student record (as before)
        s = db.query(Student).filter_by(student_id=sid).first()
        if not s:
            meta = {}
            if class_code:
                meta["class_code"] = class_code
            s = Student(student_id=sid, name=name or "", meta=json.dumps(meta) if meta else None)
            db.add(s)
            db.commit()
        else:
            changed = False
            if name and s.name != name:
                s.name = name
                changed = True
            try:
                curmeta = json.loads(s.meta) if s.meta else {}
            except Exception:
                curmeta = {}
            if class_code and curmeta.get("class_code") != class_code:
                curmeta["class_code"] = class_code
                s.meta = json.dumps(curmeta)
                changed = True
            if changed:
                db.commit()

        recorded = False
        if status == "present":
            # Use mark_attendance_once to avoid duplicates and broadcast
            try:
                recorded = mark_attendance_once(db, sid, class_code, int(period_id) if period_id is not None else None, source=source)
            except Exception:
                # fallback to inserting a record directly if mark_attendance_once fails
                try:
                    rec = Attendance(student_id=sid, timestamp=dt or datetime.datetime.utcnow(), source=source, note=note, class_code=class_code, period_id=period_id)
                    db.add(rec)
                    db.commit()
                    recorded = True
                except Exception:
                    recorded = False

        
        class_summary = None
        if class_code:
            try:
                class_summary = compute_class_summary(class_code)
            except Exception:
                class_summary = None

        return jsonify({"ok": True, "student_id": sid, "recorded": bool(recorded), "class_summary": class_summary})
    finally:
        db.close()

@app.route("/api/periods/<int:period_id>/attendance", methods=["GET"])
def api_period_attendance(period_id: int):
    """
    Return attendance records for a given period_id:
      { period_id, class_code, attendance: [ { student_id, name, timestamp, source } ... ] }
    """
    db = SessionLocal()
    try:
        rows = db.query(Attendance).filter_by(period_id=period_id).order_by(Attendance.timestamp.asc()).all()
        if not rows:
            return jsonify({"period_id": period_id, "attendance": []})
        # fetch student names in batch
        student_ids = [r.student_id for r in rows]
        students = db.query(Student).filter(Student.student_id.in_(student_ids)).all()
        name_map = {s.student_id: (s.name or "") for s in students}
        attendance = []
        for r in rows:
            attendance.append({
                "student_id": r.student_id,
                "name": name_map.get(r.student_id, ""),
                "timestamp": r.timestamp.isoformat(),
                "source": r.source,
                "note": r.note,
                "class_code": r.class_code
            })
        return jsonify({"period_id": period_id, "attendance": attendance})
    finally:
        db.close()

# --- Enroll ---

@app.route("/api/enroll", methods=["POST"])
def api_enroll():
    """
    Enroll a student using single or multiple images.
    - student_id (required)
    - name (optional)
    - email (optional, stored in meta if you wish later)
    - 'images' (multi) OR 'image' (single)
    """
    student_id = request.form.get("student_id") or request.args.get("student_id")
    name = request.form.get("name", "")
    
    email = request.form.get("email", "")

    if not student_id:
        return jsonify({"error": "student_id required"}), 400

    files = []
    if "images" in request.files:
        files = request.files.getlist("images")
    elif "image" in request.files:
        files = [request.files["image"]]

    if not files:
        return jsonify({"error": "no image file provided (key 'image' or 'images')"}), 400

    saved_files = []
    try:
        for f in files:
            filename = secure_filename(f.filename) or f"{student_id}.jpg"
            safe_name = f"{student_id}_{filename}"
            dest = os.path.join(DATA_DIR, safe_name)

            img_bytes = f.read()
            try:
                Image.open(io.BytesIO(img_bytes)).verify()
            except Exception:
                pass

            with open(dest, "wb") as fh:
                fh.write(img_bytes)
            saved_files.append(dest)
    except Exception as ex:
        return jsonify({"error": f"failed saving image(s): {ex}"}), 500

    try:
        ensure_student(student_id, name)
    except Exception as ex:
        return jsonify({"error": f"failed updating student record: {ex}"}), 500

    embedding_path = None
    if HAS_RECOGNITION and (enroll_image or enroll_images):
        try:
            if len(saved_files) > 1 and enroll_images is not None:
                embedding_path = enroll_images(student_id, saved_files)
            elif enroll_image is not None:
                embedding_path = enroll_image(student_id, saved_files[0])
        except Exception as ex:
            return jsonify({
                "ok": True,
                "student_id": student_id,
                "images_saved": [os.path.basename(p) for p in saved_files],
                "embedding_error": str(ex),
            }), 200
    else:
        return jsonify({
            "ok": True,
            "student_id": student_id,
            "images_saved": [os.path.basename(p) for p in saved_files],
            "note": "recognition module not available; embedding not created",
        }), 200

    return jsonify({
        "ok": True,
        "student_id": student_id,
        "images_saved": [os.path.basename(p) for p in saved_files],
        "embedding_saved": os.path.relpath(embedding_path, BASE_DIR) if embedding_path else None,
    }), 200

# --- Recognize ---

@app.route("/api/recognize", methods=["POST"])
def api_recognize():
    """
    Expects:
      - image (file)
      - class_code (optional)
      - period_id (optional)
    """
    if "image" not in request.files:
        return jsonify({"matches": []})

    f = request.files["image"]
    try:
        img = Image.open(io.BytesIO(f.read())).convert("RGB")
    except Exception as ex:
        return jsonify({"error": f"invalid image: {ex}"}), 400

    class_code = request.form.get("class_code")
    period_id_raw = request.form.get("period_id")
    try:
        period_id = int(period_id_raw) if period_id_raw is not None else None
    except Exception:
        period_id = None

    matches_out: List[Dict[str, Any]] = []

    if HAS_RECOGNITION and recognize_frame:
        try:
            recs = recognize_frame(img)  # list of {student_id, confidence, bbox}
        except Exception as ex:
            return jsonify({"error": f"recognition error: {ex}"}), 500

        db = SessionLocal()
        try:
            for m in recs:
                sid = m.get("student_id")
                conf = float(m.get("confidence", 0))
                recorded = False
                if sid:
                    if period_id is not None:
                        try:
                            recorded = mark_attendance_once(db, sid, class_code, period_id, source="camera")
                        except Exception:
                            recorded = False
                    matches_out.append({
                        "student_id": sid,
                        "confidence": conf,
                        "recorded": recorded,
                    })
        finally:
            db.close()
    else:
        matches_out = []

    return jsonify({"matches": matches_out})

# --- Static data files ---

@app.route("/data/<path:filename>", methods=["GET"])
def serve_data(filename):
    return send_from_directory(DATA_DIR, filename, as_attachment=False)

# --- Classes & periods ---

@app.route("/api/classes", methods=["GET", "POST"])
def api_classes():
    if request.method == "POST":
        payload = request.get_json(force=True, silent=True) or {}
        code = payload.get("code")
        name = payload.get("name", "")
        teacher = payload.get("teacher", "")
        if not code:
            return jsonify({"error": "class code required"}), 400
        ensure_class(code, name, teacher)
        return jsonify({"ok": True, "code": code})
    else:
        db = SessionLocal()
        try:
            rows = db.query(ClassRoom).order_by(ClassRoom.code).all()
            out = [{"code": r.code, "name": r.name, "teacher": r.teacher} for r in rows]
            return jsonify({"classes": out})
        finally:
            db.close()

@app.route("/api/periods", methods=["GET", "POST"])
def api_periods():
    if request.method == "POST":
        payload = request.get_json(force=True, silent=True) or {}
        class_code = payload.get("class_code")
        start_iso = payload.get("start_time")
        end_iso = payload.get("end_time")
        weekday = payload.get("weekday")
        if not class_code:
            return jsonify({"error": "class_code required"}), 400
        try:
            start_time = datetime.datetime.fromisoformat(start_iso) if start_iso else None
        except Exception:
            start_time = None
        try:
            end_time = datetime.datetime.fromisoformat(end_iso) if end_iso else None
        except Exception:
            end_time = None
        rec = create_period(class_code, start_time, end_time, weekday)
        return jsonify({"ok": True, "period": rec})
    else:
        teacher_id = request.args.get("teacher_id")
        db = SessionLocal()
        try:
            # optional filter by teacher_id
            if teacher_id:
                rows = (
                    db.query(Period, ClassRoom)
                    .join(ClassRoom, Period.class_code == ClassRoom.code)
                    .filter(ClassRoom.teacher == teacher_id)
                    .order_by(Period.created_at.desc())
                    .all()
                )
                out = [period_to_dict(p, cls) for (p, cls) in rows]
            else:
                rows = db.query(Period).order_by(Period.created_at.desc()).all()
                out = [period_to_dict(p, None) for p in rows]
            return jsonify({"periods": out})
        finally:
            db.close()

@app.route("/api/periods/<int:period_id>/start", methods=["POST"])
def api_period_start(period_id: int):
    ok = set_period_active(period_id, True)
    if not ok:
        return jsonify({"error": "period not found"}), 404
    broadcast_event({
        "type": "period_started",
        "period_id": period_id,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    })
    return jsonify({"ok": True, "period_id": period_id})

@app.route("/api/periods/<int:period_id>/stop", methods=["POST"])
def api_period_stop(period_id: int):
    ok = set_period_active(period_id, False)
    if not ok:
        return jsonify({"error": "period not found"}), 404
    broadcast_event({
        "type": "period_stopped",
        "period_id": period_id,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    })
    return jsonify({"ok": True, "period_id": period_id})

@app.route("/api/teacher/current_period", methods=["GET"])
def api_teacher_current_period():
    """
    Robust current/next period lookup:
      - Uses Period.weekday (Mon/Tue/...) case-insensitive
      - Uses only the time portion of start_time/end_time (ignores DB date)
      - Supports overnight ranges (end < start)
      - Returns `current` and `next` correctly and is defensive about missing fields
    """
    now = datetime.datetime.now()  # local time
    weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    today_short = weekday_names[now.weekday()]
    now_minutes = now.hour * 60 + now.minute

    db = SessionLocal()
    try:
        # fetch periods and optional class info if ClassRoom exists
        
        rows = (
            db.query(Period, ClassRoom)
            .join(ClassRoom, Period.class_code == ClassRoom.code)
            .all()
        )

        running = []
        future = []

        def time_to_minutes(t):
            if isinstance(t, datetime.time):
                return t.hour * 60 + t.minute
            try:
                tt = t.time()
                return tt.hour * 60 + tt.minute
            except Exception:
                return None

        for p, cls in rows:
            wd = (getattr(p, "weekday", "") or "").strip()
            if not wd:
                continue
            wd_list = [w.strip().title()[:3] for w in wd.replace(",", " ").split()]
            if today_short not in wd_list:
                continue

            s_min = time_to_minutes(getattr(p, "start_time", None))
            e_min = time_to_minutes(getattr(p, "end_time", None))
            if s_min is None or e_min is None:
                continue

            if s_min <= e_min:
                if s_min <= now_minutes <= e_min:
                    running.append((s_min, p, cls))
                elif s_min > now_minutes:
                    future.append((s_min, p, cls))
            else:
                # overnight
                if now_minutes >= s_min or now_minutes <= e_min:
                    running.append((s_min, p, cls))
                else:
                    future.append((s_min, p, cls))

        current_period = None
        next_period = None

        if running:
            running.sort(key=lambda x: x[0])
            _, p, cls = running[0]
            # safe reads with getattr
            class_code = getattr(p, "class_code", None) or ""
            class_name = ""
            if cls is not None:
                class_name = getattr(cls, "name", "") or class_code
            else:
                class_name = class_code
            start_time = getattr(p, "start_time", None)
            end_time = getattr(p, "end_time", None)
            current_period = {
                "id": getattr(p, "id", None),
                "class_code": class_code,
                "class_name": class_name,
                "start_time": start_time.time().strftime("%H:%M") if start_time else "",
                "end_time": end_time.time().strftime("%H:%M") if end_time else "",
                # safe access to room (Period may not have it)
                "room": getattr(p, "room", "") or "",
                "weekday": getattr(p, "weekday", "")
            }

        if future:
            future.sort(key=lambda x: x[0])
            _, p, cls = future[0]
            class_code = getattr(p, "class_code", None) or ""
            if cls is not None:
                class_name = getattr(cls, "name", "") or class_code
            else:
                class_name = class_code
            start_time = getattr(p, "start_time", None)
            end_time = getattr(p, "end_time", None)
            next_period = {
                "id": getattr(p, "id", None),
                "class_code": class_code,
                "class_name": class_name,
                "start_time": start_time.time().strftime("%H:%M") if start_time else "",
                "end_time": end_time.time().strftime("%H:%M") if end_time else "",
                "room": getattr(p, "room", "") or "",
                "weekday": getattr(p, "weekday", "")
            }

        return jsonify({"current": current_period, "next": next_period})
    finally:
        db.close()


@app.route("/api/upload_timetable", methods=["POST"])
def upload_timetable():
    """
    Accept CSV timetable and create classes + periods.

    Expected columns (case-insensitive, flexible):
      - class_code / subject_code / code / class
      - subject_name / subject / name  (optional)
      - weekday / day                  (Mon/Tue/Wednesday/...)
      - start_time / from / from_time  (e.g., 09:00 or 9:00 AM)
      - end_time / to / to_time
      - room / classroom               (optional)
      - teacher_id / teacher / faculty (optional; if missing, defaults to 'teacher1')

    Only time-of-day and weekday are used for current/next period detection.
    """
    if "file" not in request.files:
        return jsonify({"error": "file field 'file' required"}), 400

    f = request.files["file"]
    try:
        text = f.read().decode("utf-8")
    except Exception as e:
        return jsonify({"error": "failed to read file", "detail": str(e)}), 400

    import csv, io
    reader = csv.DictReader(io.StringIO(text))

    # helper: get value ignoring case and different header names
    def get_field(row, *names):
        for name in names:
            for k, v in row.items():
                if k and k.strip().lower() == name:
                    return str(v).strip() if v is not None else ""
        return ""

    weekday_map = {
        "mon": "Mon", "monday": "Mon",
        "tue": "Tue", "tuesday": "Tue",
        "wed": "Wed", "wednesday": "Wed",
        "thu": "Thu", "thursday": "Thu",
        "fri": "Fri", "friday": "Fri",
        "sat": "Sat", "saturday": "Sat",
        "sun": "Sun", "sunday": "Sun",
    }

    db = SessionLocal()
    created = 0
    try:
        for row in reader:
            class_code = get_field(row, "class_code", "subject_code", "code", "class")
            subject_name = get_field(row, "subject_name", "subject", "name","class_name")
            weekday_raw = get_field(row, "weekday", "day")
            start_str = get_field(row, "start_time", "from", "from_time")
            end_str = get_field(row, "end_time", "to", "to_time")
            room = get_field(row, "room", "classroom")
            teacher_id = (
                get_field(row, "teacher_id", "teacher", "faculty")
                or request.form.get("teacher_id", "teacher1")
            )

            # skip incomplete lines
            if not class_code or not weekday_raw or not start_str or not end_str:
                continue

            # normalize weekday to Mon/Tue/...
            wd_key = weekday_raw.lower()
            weekday = weekday_map.get(wd_key, weekday_raw[:3].title())

            # parse times: support "09:00" and "9:00 AM"
            today = datetime.date.today()
            try:
                try:
                    st = datetime.datetime.strptime(start_str, "%H:%M").time()
                except ValueError:
                    st = datetime.datetime.strptime(start_str, "%I:%M %p").time()
                try:
                    et = datetime.datetime.strptime(end_str, "%H:%M").time()
                except ValueError:
                    et = datetime.datetime.strptime(end_str, "%I:%M %p").time()
            except Exception:
                # invalid time; skip this row
                continue

            start_dt = datetime.datetime.combine(today, st)
            end_dt = datetime.datetime.combine(today, et)

            # ensure class exists and is linked to teacher
            ensure_class(class_code, name=subject_name, teacher=teacher_id)

            # create period
            p = Period(
                class_code=class_code,
                start_time=start_dt,
                end_time=end_dt,
                weekday=weekday,
                room=room,
                active=False,
            )
            db.add(p)
            created += 1

        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({"error": "failed to import", "detail": str(e)}), 500
    finally:
        db.close()

    return jsonify({"ok": True, "created_periods": created})

from flask import Response, stream_with_context

@app.route("/api/events", methods=["GET"])
def api_events():
    """
    Server-Sent Events (SSE) endpoint.
    Clients connect and receive JSON messages as `data: {...}\n\n`.
    """
    def gen(q: queue.Queue):
        try:
            while True:
                payload = q.get()  # blocking
                yield f"data: {payload}\n\n"
        except GeneratorExit:
            # client closed connection
            return

    q = queue.Queue()
    clients.append(q)

    # When Response is closed, queue remains in clients; we don't strictly remove it here
    return Response(stream_with_context(gen(q)), mimetype="text/event-stream")

# --- Run server ---

if __name__ == "__main__":
    print("Starting SAMS backend on http://127.0.0.1:5000")

    if not HAS_RECOGNITION:
        print("Note: recognition module not available")

    app.run(host="0.0.0.0", port=5000, debug=True)
