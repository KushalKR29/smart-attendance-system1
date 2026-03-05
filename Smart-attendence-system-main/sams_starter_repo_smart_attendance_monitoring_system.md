# SAMS - Starter Repo (Smart Attendance Monitoring System)

This document contains a minimal, working **starter repository** for a Smart Attendance Monitoring System (SAMS) using facial recognition. It includes a Flask backend (enrollment + recognition), a simple frontend (webcam capture + dashboard), Docker setup, and instructions to run locally as a prototype.

> **Goal:** Provide a runnable prototype you can extend: enroll student faces, run webcam recognition in a classroom demo, and show per-student attendance updates.

---

## File structure

```
SAMS-starter/
├─ README.md
├─ docker-compose.yml
├─ backend/
│  ├─ Dockerfile
│  ├─ requirements.txt
│  ├─ app.py
│  ├─ recognition.py
│  ├─ models.py
│  └─ data/ (created at runtime)
└─ frontend/
   ├─ Dockerfile
   ├─ index.html
   └─ app.js
```

---

## README.md

```markdown
# SAMS - Starter Prototype

## Overview
This starter repo builds a minimal prototype for Smart Attendance Monitoring System using facial recognition.

**Features**
- Enroll student images -> stored embeddings
- Recognize faces from webcam frames -> mark attendance
- Simple student dashboard showing attendance history

**Tech stack (prototype)**
- Backend: Flask (Python)
- Facial recognition: `face_recognition` (dlib-based) OR placeholder if not available
- DB: SQLite (simple file based)
- Frontend: plain HTML + JS (webcam capture + live roster)

## Quick run (local)

1. Install Python 3.8+ and Docker (optional).
2. If running locally without Docker, create a virtualenv and install requirements:

```bash
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
```

3. Start the backend:

```bash
cd backend
python app.py
```

4. Open `frontend/index.html` in a browser (or run frontend as static server) and enroll a student and try recognition.

## Notes
- `face_recognition` requires `dlib` and system build tools; if you can't install, mock the recognition module in `recognition.py` (a fallback stub is provided in comments).
- This repo is a prototype: production must add authentication, HTTPS, secure storage, and privacy compliance.
```
```

---

## backend/requirements.txt

```text
Flask==2.1.3
flask-cors==3.0.10
numpy==1.24.0
pillow==9.4.0
face_recognition==1.3.0
sqlalchemy==1.4.46
```

> If `face_recognition` fails to install, use the stub in `recognition.py` (already included).

---

## backend/models.py

```python
# models.py
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime

Base = declarative_base()

class Student(Base):
    __tablename__ = 'students'
    id = Column(Integer, primary_key=True)
    student_id = Column(String, unique=True, nullable=False)
    name = Column(String)
    embedding_path = Column(String)

class Attendance(Base):
    __tablename__ = 'attendance'
    id = Column(Integer, primary_key=True)
    student_id = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    source = Column(String)  # e.g., 'camera'


def get_session(db_path='sqlite:///sams.db'):
    engine = create_engine(db_path, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()
```

---

## backend/recognition.py

```python
# recognition.py
# Provides enrollment and recognition functions using face_recognition.

import os
import numpy as np
from PIL import Image

try:
    import face_recognition
    REAL = True
except Exception as e:
    # If face_recognition isn't available, use a simple stub for dev/testing.
    REAL = False
    print('WARNING: face_recognition not available — using stub matcher.')

EMBED_DIR = 'data/embeddings'
os.makedirs(EMBED_DIR, exist_ok=True)


def _save_embedding(student_id, embedding):
    path = os.path.join(EMBED_DIR, f"{student_id}.npy")
    np.save(path, embedding)
    return path


def enroll_image(student_id, image_path):
    """Process an image file, compute embedding, and save it."""
    if REAL:
        img = face_recognition.load_image_file(image_path)
        boxes = face_recognition.face_locations(img)
        if len(boxes) == 0:
            raise ValueError('No face found in enrollment image')
        encodings = face_recognition.face_encodings(img, boxes)
        emb = np.mean(encodings, axis=0)
    else:
        # stub: generate deterministic pseudo-embedding from file
        emb = np.frombuffer(open(image_path, 'rb').read()[:128].ljust(128, b'0'), dtype=np.uint8).astype(np.float32)
        emb = emb / (np.linalg.norm(emb) + 1e-6)

    path = _save_embedding(student_id, emb)
    return path


def load_all_embeddings():
    records = []
    for fname in os.listdir(EMBED_DIR):
        if fname.endswith('.npy'):
            sid = fname[:-4]
            emb = np.load(os.path.join(EMBED_DIR, fname))
            records.append((sid, emb))
    return records


def recognize_frame(frame_image, threshold=0.55):
    """Given a PIL image or numpy array, detect faces and match to enrolled.
    Returns list of dicts: {student_id, confidence, bbox}
    """
    results = []
    if REAL:
        img = np.array(frame_image)
        boxes = face_recognition.face_locations(img)
        encs = face_recognition.face_encodings(img, boxes)
    else:
        # stub: pretend one face with pseudo embedding derived from bytes
        encs = []
        emb = np.frombuffer(frame_image.tobytes()[:128].ljust(128, b'0'), dtype=np.uint8).astype(np.float32)
        emb = emb / (np.linalg.norm(emb) + 1e-6)
        encs = [emb]
        boxes = [(0, frame_image.width, frame_image.height, 0)]

    enrolled = load_all_embeddings()
    for bbox, enc in zip(boxes, encs):
        best = None
        best_dist = 999
        for sid, e in enrolled:
            # cosine distance approximate via dot product since embeddings are normalized
            # compute euclidean distance if not normalized
            dist = np.linalg.norm(e - enc)
            if dist < best_dist:
                best_dist = dist
                best = sid
        if best is not None and best_dist <= threshold:
            results.append({
                'student_id': best,
                'confidence': float(1 - best_dist),
                'bbox': bbox
            })
    return results
```

---

## backend/app.py

```python
# app.py
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
from recognition import enroll_image, recognize_frame
from models import get_session, Student, Attendance
from PIL import Image
import io

app = Flask(__name__)
CORS(app)

session = get_session('sqlite:///backend/sams.db')

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(DATA_DIR, exist_ok=True)


@app.route('/api/enroll', methods=['POST'])
def enroll():
    """Enroll student by student_id + image file (multipart form)"""
    student_id = request.form.get('student_id')
    name = request.form.get('name', '')
    if 'image' not in request.files:
        return jsonify({'error': 'no image'}), 400
    img = request.files['image']
    img_bytes = img.read()
    img_path = os.path.join(DATA_DIR, f'{student_id}.jpg')
    with open(img_path, 'wb') as f:
        f.write(img_bytes)
    emb_path = enroll_image(student_id, img_path)

    # add to DB if not exists
    s = session.query(Student).filter_by(student_id=student_id).first()
    if not s:
        s = Student(student_id=student_id, name=name, embedding_path=emb_path)
        session.add(s)
    else:
        s.embedding_path = emb_path
    session.commit()
    return jsonify({'ok': True, 'student_id': student_id})


@app.route('/api/recognize', methods=['POST'])
def recognize():
    """Recognize faces from a posted image (multipart/form) and mark attendance"""
    if 'image' not in request.files:
        return jsonify({'error': 'no image'}), 400
    img = request.files['image']
    img_pil = Image.open(io.BytesIO(img.read())).convert('RGB')
    matches = recognize_frame(img_pil)
    results = []
    for m in matches:
        student_id = m['student_id']
        a = Attendance(student_id=student_id, source='camera')
        session.add(a)
        results.append(m)
    session.commit()
    return jsonify({'matches': results})


@app.route('/api/attendance/<student_id>', methods=['GET'])
def attendance_history(student_id):
    recs = session.query(Attendance).filter_by(student_id=student_id).order_by(Attendance.timestamp.desc()).all()
    out = [{'timestamp': r.timestamp.isoformat(), 'source': r.source} for r in recs]
    return jsonify({'student_id': student_id, 'history': out})


@app.route('/api/students', methods=['GET'])
def list_students():
    students = session.query(Student).all()
    out = [{'student_id': s.student_id, 'name': s.name} for s in students]
    return jsonify({'students': out})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
```

---

## frontend/index.html

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>SAMS Demo</title>
  <style>
    body { font-family: Arial, sans-serif; padding: 16px }
    #video { border: 1px solid #ccc }
    .controls { margin-top: 8px }
  </style>
</head>
<body>
  <h2>SAMS — Demo</h2>
  <div>
    <video id="video" width="480" height="360" autoplay muted></video>
  </div>
  <div class="controls">
    <input id="studentId" placeholder="student id" />
    <input id="studentName" placeholder="name (optional)" />
    <button id="enrollBtn">Enroll (capture)</button>
    <button id="recognizeBtn">Recognize (capture)</button>
  </div>
  <pre id="log"></pre>

  <script src="app.js"></script>
</body>
</html>
```

---

## frontend/app.js

```javascript
// app.js — simple webcam capture + calls backend endpoints
const video = document.getElementById('video');
const enrollBtn = document.getElementById('enrollBtn');
const recognizeBtn = document.getElementById('recognizeBtn');
const studentIdInput = document.getElementById('studentId');
const studentNameInput = document.getElementById('studentName');
const log = document.getElementById('log');

async function init() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    video.srcObject = stream;
  } catch (e) {
    log.innerText = 'Error accessing camera: ' + e;
  }
}

function captureBlob() {
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth || 480;
  canvas.height = video.videoHeight || 360;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg'));
}

async function enroll() {
  const student_id = studentIdInput.value.trim();
  const name = studentNameInput.value.trim();
  if (!student_id) { alert('enter student id'); return; }
  const blob = await captureBlob();
  const fd = new FormData();
  fd.append('student_id', student_id);
  fd.append('name', name);
  fd.append('image', blob, 'capture.jpg');
  const res = await fetch('http://localhost:5000/api/enroll', { method: 'POST', body: fd });
  const j = await res.json();
  log.innerText = JSON.stringify(j, null, 2);
}

async function recognize() {
  const blob = await captureBlob();
  const fd = new FormData();
  fd.append('image', blob, 'capture.jpg');
  const res = await fetch('http://localhost:5000/api/recognize', { method: 'POST', body: fd });
  const j = await res.json();
  log.innerText = JSON.stringify(j, null, 2);
}

enrollBtn.onclick = enroll;
recognizeBtn.onclick = recognize;

init();
```

---

## docker-compose.yml

```yaml
version: '3.8'
services:
  backend:
    build: ./backend
    ports:
      - '5000:5000'
    volumes:
      - ./backend/data:/app/data
  frontend:
    image: nginx:alpine
    volumes:
      - ./frontend:/usr/share/nginx/html:ro
    ports:
      - '8080:80'
```

---

## backend/Dockerfile

```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y build-essential libsndfile1 git && rm -rf /var/lib/apt/lists/*
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
COPY . /app
EXPOSE 5000
CMD ["python", "app.py"]
```

---

## frontend/Dockerfile

```dockerfile
# optional if you want frontend built as container - but docker-compose uses nginx image
FROM node:18-alpine as build
WORKDIR /app
COPY . /app
RUN echo "frontend ready"
```

---

## Next steps & checklist

- [ ] Try running locally. If `face_recognition` can't be installed, use stub mode (app prints warning). The stub allows UI testing but not robust recognition.
- [ ] Enroll at least 3 students with good frontal photos.
- [ ] Test recognition under classroom-like lighting and adjust `threshold` in `recognition.py`.
- [ ] Add authentication (JWT), HTTPS, and role-based UI.
- [ ] Improve model: switch from `face_recognition` to ArcFace / FaceNet for higher accuracy; add preprocessing (alignment) and augmentation.
- [ ] Add WebSocket to push live roster updates to teacher dashboard.


---

## License

Prototype for educational use. Not for production as-is. Add appropriate privacy notices and consents before deploying.

