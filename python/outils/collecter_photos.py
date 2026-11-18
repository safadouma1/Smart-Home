"""Capture des photos d'une personne avec la webcam (sans l'interface).

    python outils/collecter_photos.py <nom>

Le plus simple reste le bouton « Ajouter mon visage » de l'application.
"""
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smarthome.config import CAMERA_INDEX, DATA_DIR  # noqa: E402

NB_PHOTOS = 300

if len(sys.argv) < 2:
    raise SystemExit('Utilisation : python outils/collecter_photos.py <nom>')
name = sys.argv[1].strip().lower()
person_dir = DATA_DIR / name
person_dir.mkdir(parents=True, exist_ok=True)

cap = cv2.VideoCapture(CAMERA_INDEX)
if not cap.isOpened():
    raise SystemExit("Erreur : impossible d'ouvrir la webcam.")

while True:  # attendre que la personne soit prête
    ret, frame = cap.read()
    if not ret:
        continue
    cv2.putText(frame, f'{name} : pret ? Appuyez sur "Q"', (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2, cv2.LINE_AA)
    cv2.imshow('frame', frame)
    if cv2.waitKey(25) & 0xFF == ord('q'):
        break

counter = 0
while counter < NB_PHOTOS:
    ret, frame = cap.read()
    if not ret:
        continue
    cv2.imshow('frame', frame)
    cv2.waitKey(25)
    cv2.imwrite(str(person_dir / f'{counter}.jpg'), frame)
    counter += 1

cap.release()
cv2.destroyAllWindows()
print(f'{counter} photos enregistrées dans {person_dir}.')
print('Ensuite : python outils/creer_dataset.py  puis  python outils/entrainer_modele.py')
