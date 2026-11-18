"""Code partagé : détection du visage, caractéristiques, dataset et modèle.

Chaque personne a son propre dossier d'images : data/photos/<nom>/.
Les mêmes fonctions servent au dataset, à l'entraînement et à l'application,
pour que le modèle reçoive toujours le même type de données.
"""
import os
import pickle

import cv2
import mediapipe as mp
import numpy as np

from .config import DATA_DIR, DATASET_FILE, FACE_SIZE, MODEL_DIR, MODEL_FILE

# Descripteur HOG : forme du visage, robuste aux variations de lumière
_hog = cv2.HOGDescriptor((FACE_SIZE, FACE_SIZE), (16, 16), (8, 8), (8, 8), 9)


# --------------------------------------------------------------- détection
def create_face_detector(min_confidence=0.5):
    return mp.solutions.face_detection.FaceDetection(
        model_selection=0, min_detection_confidence=min_confidence)


def detect_faces(detector, frame_bgr):
    """Retourne la liste des boîtes (x1, y1, x2, y2) des visages détectés."""
    h, w = frame_bgr.shape[:2]
    results = detector.process(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    boxes = []
    for det in results.detections or []:
        b = det.location_data.relative_bounding_box
        x1 = max(int(b.xmin * w), 0)
        y1 = max(int(b.ymin * h), 0)
        x2 = min(int((b.xmin + b.width) * w), w)
        y2 = min(int((b.ymin + b.height) * h), h)
        if x2 - x1 > 10 and y2 - y1 > 10:
            boxes.append((x1, y1, x2, y2))
    return boxes


def largest_face(boxes):
    return max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1])) if boxes else None


def face_features(frame_bgr, box):
    """Recadre le visage, le normalise et retourne son vecteur HOG."""
    x1, y1, x2, y2 = box
    face = cv2.cvtColor(frame_bgr[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    face = cv2.resize(face, (FACE_SIZE, FACE_SIZE))
    face = cv2.equalizeHist(face)
    return _hog.compute(face).flatten()


# ----------------------------------------------------------------- dataset
def load_dataset():
    if not os.path.exists(DATASET_FILE):
        return [], []
    with open(DATASET_FILE, 'rb') as f:
        d = pickle.load(f)
    return list(d['data']), [str(label) for label in d['labels']]


def save_dataset(data, labels):
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATASET_FILE, 'wb') as f:
        pickle.dump({'data': data, 'labels': labels}, f)


def build_dataset_from_images(progress=print):
    """Recalcule data.pickle à partir de toutes les images de data/photos/<nom>/."""
    detector = create_face_detector(min_confidence=0.3)
    data, labels, skipped = [], [], 0
    for name in sorted(os.listdir(DATA_DIR)):
        person_dir = os.path.join(DATA_DIR, name)
        if not os.path.isdir(person_dir):
            continue
        progress(f'Traitement de {name}...')
        for img_name in os.listdir(person_dir):
            img = cv2.imread(os.path.join(person_dir, img_name))
            box = largest_face(detect_faces(detector, img)) if img is not None else None
            if box is None:
                skipped += 1
                continue
            data.append(face_features(img, box))
            labels.append(name)
    save_dataset(data, labels)
    return len(data), skipped


# ------------------------------------------------------------------ modèle
def train_model(data, labels):
    """Entraîne le classifieur. Retourne (modèle, précision sur le test)."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score
    from sklearn.model_selection import train_test_split

    x = np.asarray(data)
    y = np.asarray(labels)
    if len(set(labels)) < 2:
        raise ValueError('Il faut au moins 2 personnes pour entraîner le modèle.')

    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.2, shuffle=True, stratify=y, random_state=42)
    model = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
    model.fit(x_train, y_train)
    score = accuracy_score(y_test, model.predict(x_test))

    # Modèle final entraîné sur toutes les données
    model.fit(x, y)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODEL_FILE, 'wb') as f:
        pickle.dump({'model': model}, f)
    return model, score


def load_model():
    if not os.path.exists(MODEL_FILE):
        return None
    with open(MODEL_FILE, 'rb') as f:
        return pickle.load(f)['model']


def predict(model, features, min_confidence=0.6):
    """Retourne (nom, confiance). Nom = None si la personne est inconnue."""
    proba = model.predict_proba([features])[0]
    best = int(proba.argmax())
    name = str(model.classes_[best])
    return (name if proba[best] >= min_confidence else None), float(proba[best])
