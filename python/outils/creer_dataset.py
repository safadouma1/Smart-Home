"""Recalcule data/modele/data.pickle à partir de toutes les photos de data/photos/<nom>/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smarthome.config import DATASET_FILE  # noqa: E402
from smarthome.face_model import build_dataset_from_images  # noqa: E402

count, skipped = build_dataset_from_images()
print(f'{count} visages enregistrés dans {DATASET_FILE} ({skipped} images ignorées).')
