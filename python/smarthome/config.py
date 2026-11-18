"""Réglages de l'application Smart Home (chemins, caméra, Arduino, reconnaissance)."""
from pathlib import Path

# ----------------------------------------------------------- dossiers
PYTHON_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PYTHON_DIR / 'data' / 'photos'          # une sous-dossier par personne
MODEL_DIR = PYTHON_DIR / 'data' / 'modele'
DATASET_FILE = MODEL_DIR / 'data.pickle'           # caractéristiques des visages
MODEL_FILE = MODEL_DIR / 'model.p'                 # modèle entraîné

# ------------------------------------------------------------ Arduino
BAUDRATE = 9600                 # doit être identique à Serial.begin() dans l'Arduino
NO_DATA_TIMEOUT_S = 5           # au-delà : « En attente de données »

# ------------------------------------------------- reconnaissance faciale
CAMERA_INDEX = 0                # 0 = webcam intégrée, 1 = webcam USB...
FACE_SIZE = 64                  # taille du visage recadré (pixels)
RECOGNITION_CONFIDENCE = 0.6    # en dessous : « Inconnu »
STABLE_FRAMES = 6               # analyses identiques avant de valider une personne
ENROLL_SAMPLES = 200            # photos prises pour ajouter une personne

# ------------------------------------------------------------- porte
DOOR_AUTO_CLOSE_MS = 10_000     # la porte se referme après 10 s
FACE_COOLDOWN_S = 15            # délai minimum entre deux ouvertures par visage

# ------------------------------------------------- seuils d'affichage
TEMP_WARN = 30                  # °C (même seuil que le ventilateur de l'Arduino)
TEMP_ALERT = 35
