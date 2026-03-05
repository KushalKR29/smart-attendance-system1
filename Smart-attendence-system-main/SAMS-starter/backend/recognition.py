# recognition.py
import os
import numpy as np
from PIL import Image

try:
    import face_recognition
    REAL = True
except Exception:
    REAL = False
    print('WARNING: face_recognition not available — using stub matcher.')

EMBED_DIR = os.path.join(os.path.dirname(__file__), 'data', 'embeddings')
os.makedirs(EMBED_DIR, exist_ok=True)

def _save_embedding(student_id, embedding):
    path = os.path.join(EMBED_DIR, f"{student_id}.npy")
    np.save(path, embedding)
    return path

def _image_to_embedding(image_path):
    """
    Given a path to an image file, compute and return an embedding (1D numpy array).
    """
    if REAL:
        img = face_recognition.load_image_file(image_path)
        boxes = face_recognition.face_locations(img)
        if len(boxes) == 0:
            raise ValueError(f'No face found in image: {image_path}')
        encodings = face_recognition.face_encodings(img, boxes)
        # average encodings if more than one face is detected (unlikely for enrollment)
        emb = np.mean(encodings, axis=0)
    else:
        # stub deterministic embedding from file bytes (for dev)
        data = open(image_path, 'rb').read()
        arr = np.frombuffer(data[:128].ljust(128, b'0'), dtype=np.uint8).astype(np.float32)
        emb = arr / (np.linalg.norm(arr) + 1e-6)
    # normalize
    emb = emb / (np.linalg.norm(emb) + 1e-6)
    return emb

def enroll_image(student_id, image_path):
    """
    Backwards-compatible single-image enrollment: compute embedding and save.
    """
    emb = _image_to_embedding(image_path)
    return _save_embedding(student_id, emb)

def enroll_images(student_id, image_paths):
    """
    Given multiple image paths, compute per-image embeddings, average them,
    then save a single embedding file for the student.
    Returns embedding path.
    """
    if not image_paths:
        raise ValueError("No images provided for enrollment")
    embs = []
    last_errors = []
    for p in image_paths:
        try:
            e = _image_to_embedding(p)
            embs.append(e)
        except Exception as ex:
            # collect errors but continue if at least one image succeeds
            last_errors.append(str(ex))
    if len(embs) == 0:
        raise ValueError("All enrollment images failed: " + "; ".join(last_errors))
    # average embeddings and re-normalize
    avg = np.mean(np.stack(embs, axis=0), axis=0)
    avg = avg / (np.linalg.norm(avg) + 1e-6)
    return _save_embedding(student_id, avg)

def load_all_embeddings():
    records = []
    for fname in os.listdir(EMBED_DIR):
        if fname.endswith('.npy'):
            sid = fname[:-4]
            emb = np.load(os.path.join(EMBED_DIR, fname))
            records.append((sid, emb))
    return records

def recognize_frame(frame_image, threshold=0.55):
    """
    Given a PIL image or numpy array, detect faces and match to enrolled embeddings.
    Returns list of { student_id, confidence, bbox }.
    """
    results = []
    if REAL:
        img = np.array(frame_image)
        boxes = face_recognition.face_locations(img)
        encs = face_recognition.face_encodings(img, boxes)
    else:
        
        data = frame_image.tobytes()
        arr = np.frombuffer(data[:128].ljust(128, b'0'), dtype=np.uint8).astype(np.float32)
        emb = arr / (np.linalg.norm(arr) + 1e-6)
        encs = [emb]
        boxes = [(0, frame_image.width, frame_image.height, 0)]

    enrolled = load_all_embeddings()
    for bbox, enc in zip(boxes, encs):
        best = None
        best_dist = float('inf')
        for sid, e in enrolled:
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
