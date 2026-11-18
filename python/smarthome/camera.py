"""Caméra + reconnaissance faciale + ajout d'une nouvelle personne (dans un thread)."""
import os
import queue
import re
import threading
import time

import cv2

from . import face_model as common
from .config import ENROLL_SAMPLES, RECOGNITION_CONFIDENCE, STABLE_FRAMES


def clean_name(name):
    name = re.sub(r'[^a-z0-9_-]', '', name.strip().lower().replace(' ', '_'))
    return name[:30]


class CameraWorker:
    """Lit la caméra, reconnaît les visages et envoie des événements à l'interface.

    Événements (dans self.events) :
      ('person', nom | None | '')   personne stable reconnue (None = inconnu, '' = personne)
      ('enroll', n, total)           progression de l'ajout d'un visage
      ('training', message)          entraînement en cours
      ('trained', nom, précision)    nouveau modèle prêt
      ('error', message)
    """

    def __init__(self, source=0):
        self.source = source
        self.events = queue.Queue()
        self.latest_frame = None            # dernière image (BGR) annotée
        self.camera_ok = False
        self.model = common.load_model()
        if self.model is not None:
            self.model.n_jobs = 1           # plus rapide pour une seule image
        self._stop = threading.Event()
        self._enroll_name = None
        self._enroll_data = []
        self._last_result = ('', 0.0)
        self._candidate, self._streak, self._stable = None, 0, None
        self._thread = threading.Thread(target=self._loop, daemon=True)

    # ---------------------------------------------------------- public
    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2)

    def known_people(self):
        return sorted(str(c) for c in self.model.classes_) if self.model is not None else []

    def is_busy(self):
        return self._enroll_name is not None

    def start_enroll(self, name):
        name = clean_name(name)
        if not name:
            raise ValueError('Nom invalide : utilisez des lettres ou des chiffres.')
        if self.is_busy():
            raise RuntimeError('Un ajout est déjà en cours.')
        if not self.camera_ok:
            raise RuntimeError('Caméra indisponible.')
        os.makedirs(os.path.join(common.DATA_DIR, name), exist_ok=True)
        self._enroll_data = []
        self._enroll_name = name
        return name

    # ----------------------------------------------------------- boucle
    def _open(self):
        if isinstance(self.source, int) and os.name == 'nt':
            return cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
        return cv2.VideoCapture(self.source)

    def _loop(self):
        cap = self._open()
        self.camera_ok = cap.isOpened()
        if not self.camera_ok:
            self.events.put(('error', f'Impossible d\'ouvrir la caméra ({self.source}).'))
            return
        detector = common.create_face_detector(min_confidence=0.5)
        frame_count = 0
        is_file = isinstance(self.source, str)

        while not self._stop.is_set():
            ok, frame = cap.read()
            if not ok:
                if is_file:                         # vidéo de test : on reboucle
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                time.sleep(0.05)
                continue
            if is_file:
                time.sleep(1 / 25)
            frame_count += 1

            boxes = common.detect_faces(detector, frame)
            box = common.largest_face(boxes)

            if self._enroll_name:
                self._enroll_step(frame, box, frame_count)
            elif frame_count % 3 == 0:
                self._recognize(frame, box)

            self._draw(frame, boxes, box)
            self.latest_frame = frame

        cap.release()

    # ----------------------------------------------------- reconnaissance
    def _recognize(self, frame, box):
        if box is None:
            result = ('', 0.0)
        elif self.model is None:
            result = (None, 0.0)
        else:
            result = common.predict(self.model, common.face_features(frame, box),
                                    RECOGNITION_CONFIDENCE)
        self._last_result = result

        # On ne valide une personne qu'après plusieurs analyses identiques
        if result[0] == self._candidate:
            self._streak += 1
        else:
            self._candidate, self._streak = result[0], 1
        if self._streak >= STABLE_FRAMES and self._candidate != self._stable:
            self._stable = self._candidate
            self.events.put(('person', self._stable))

    def _draw(self, frame, boxes, main_box):
        enrolling = self._enroll_name is not None
        name, conf = self._last_result
        for b in boxes:
            if enrolling:
                color, text = (246, 130, 59), self._enroll_name
            elif b != main_box or name == '':
                color, text = (160, 160, 160), ''
            elif name is None:
                color, text = (68, 68, 239), f'Inconnu {conf:.0%}'
            else:
                color, text = (94, 197, 34), f'{name} {conf:.0%}'
            x1, y1, x2, y2 = b
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
            if text:
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
                cv2.rectangle(frame, (x1, y1 - th - 14), (x1 + tw + 12, y1), color, -1)
                cv2.putText(frame, text, (x1 + 6, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                            (255, 255, 255), 2, cv2.LINE_AA)

    # ------------------------------------------------- ajout d'un visage
    def _enroll_step(self, frame, box, frame_count):
        if box is None or frame_count % 2 or len(self._enroll_data) >= ENROLL_SAMPLES:
            return              # pas de visage, ou capture terminée (entraînement en cours)
        name = self._enroll_name
        n = len(self._enroll_data)
        cv2.imwrite(os.path.join(common.DATA_DIR, name, f'{int(time.time() * 1000)}_{n}.jpg'), frame)
        self._enroll_data.append(common.face_features(frame, box))
        self.events.put(('enroll', n + 1, ENROLL_SAMPLES))
        if n + 1 >= ENROLL_SAMPLES:
            data = self._enroll_data
            threading.Thread(target=self._train, args=(name, data), daemon=True).start()

    def _train(self, name, new_data):
        try:
            self.events.put(('training', 'Entraînement du modèle...'))
            data, labels = common.load_dataset()
            data += new_data
            labels += [name] * len(new_data)
            common.save_dataset(data, labels)
            if len(set(labels)) < 2:                 # 1re personne : rien à comparer encore
                self.events.put(('saved', name))
                return
            model, score = common.train_model(data, labels)
            model.n_jobs = 1
            self.model = model
            self._stable = self._candidate = 'reset'
            self.events.put(('trained', name, score))
        except Exception as e:
            self.events.put(('error', f"Échec de l'entraînement : {e}"))
        finally:
            self._enroll_name = None
