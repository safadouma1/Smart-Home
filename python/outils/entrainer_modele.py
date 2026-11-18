"""Entraîne le modèle de reconnaissance et l'enregistre dans data/modele/model.p."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smarthome.face_model import load_dataset, train_model  # noqa: E402

data, labels = load_dataset()
print('Visages par personne :', dict(Counter(labels)))
_, score = train_model(data, labels)
print(f'{score * 100:.1f}% des échantillons de test sont correctement classés.')
