"""Communication avec l'Arduino (port série) + mode simulation.

Protocole (une ligne de texte terminée par un retour à la ligne) :

  Arduino -> PC :  T:25.3;H:60;GAZ:0;PLUIE:0;PIR:1;FAN:0;PORTE:0;FENETRE:1;GARAGE:0;RFID:0
      T, H     : température (°C) et humidité (%)
      GAZ      : 1 = gaz/fumée détecté
      PLUIE    : 1 = pluie détectée
      PIR      : 1 = mouvement détecté
      FAN      : 1 = ventilateur en marche
      PORTE    : 1 = porte ouverte
      FENETRE  : 1 = fenêtre ouverte
      GARAGE   : 1 = garage ouvert
      RFID     : 0 = aucun badge, 1 = badge autorisé, 2 = badge refusé
  Les clés absentes gardent leur dernière valeur ; les clés inconnues sont ignorées.

  PC -> Arduino :  PORTE:OUVRIR | PORTE:FERMER | FAN:ON | FAN:OFF | FAN:AUTO
                   VISAGE:<nom> | VISAGE:INCONNU
"""
import random
import threading
import time

from .config import BAUDRATE, TEMP_WARN

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pyserial absent : seule la simulation fonctionne
    serial = None
    list_ports = None

DEFAULT_STATE = {
    'T': None, 'H': None, 'GAZ': 0, 'PLUIE': 0, 'PIR': 0, 'FAN': 0,
    'PORTE': 0, 'FENETRE': 1, 'GARAGE': 0, 'RFID': 0,
}


def available_ports():
    if list_ports is None:
        return []
    return [p.device for p in list_ports.comports()]


def parse_line(line, state):
    """Met à jour `state` avec les paires CLE:valeur d'une ligne. Retourne True si valide."""
    updated = False
    for part in line.replace(',', ';').split(';'):
        if ':' not in part:
            continue
        key, value = (s.strip() for s in part.split(':', 1))
        key = key.upper()
        if key not in DEFAULT_STATE:
            continue
        try:
            state[key] = float(value) if key in ('T', 'H') else int(float(value))
            updated = True
        except ValueError:
            pass
    return updated


class SensorLink:
    """Lit l'état des capteurs dans un thread, depuis l'Arduino ou la simulation."""

    def __init__(self, on_log=print):
        self.state = dict(DEFAULT_STATE)
        self.mode = None            # None | 'serial' | 'simulation'
        self.last_update = 0.0
        self._on_log = on_log
        self._lock = threading.Lock()
        self._serial = None
        self._stop = threading.Event()
        self._thread = None
        self._fan_mode = 'AUTO'     # utilisé par la simulation

    # ---------------------------------------------------------- public
    def connect(self, port, baudrate=BAUDRATE):
        if serial is None:
            raise RuntimeError("pyserial n'est pas installé (pip install pyserial).")
        self.disconnect()
        self._serial = serial.Serial(port, baudrate, timeout=1)
        self.mode = 'serial'
        self._start(self._serial_loop)
        self._on_log(f'Connecté à {port} ({baudrate} bauds)')

    def start_simulation(self):
        self.disconnect()
        self.state.update(T=24.0, H=55.0)
        self.mode = 'simulation'
        self._start(self._simulation_loop)
        self._on_log('Mode simulation activé (aucun Arduino nécessaire)')

    def disconnect(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None
        self._thread = None
        if self.mode:
            self._on_log('Déconnecté')
        self.mode = None

    def send(self, command):
        if self.mode == 'serial' and self._serial:
            try:
                self._serial.write((command + '\n').encode())
            except Exception as e:
                self._on_log(f"Erreur d'envoi : {e}")
                return
        elif self.mode == 'simulation':
            self._simulate_command(command)
        else:
            self._on_log(f'Non connecté : commande « {command} » ignorée')
            return
        self._on_log(f'→ {command}')

    def snapshot(self):
        with self._lock:
            return dict(self.state), self.last_update

    # --------------------------------------------------------- threads
    def _start(self, target):
        self._stop = threading.Event()
        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def _serial_loop(self):
        while not self._stop.is_set():
            try:
                raw = self._serial.readline()
            except Exception as e:
                self._on_log(f'Connexion perdue : {e}')
                self.mode = None
                return
            line = raw.decode(errors='ignore').strip()
            if not line:
                continue
            with self._lock:
                if parse_line(line, self.state):
                    self.last_update = time.time()

    def _simulation_loop(self):
        while not self._stop.wait(0.8):
            with self._lock:
                s = self.state
                s['T'] = round(min(38, max(18, s['T'] + random.uniform(-0.4, 0.5))), 1)
                s['H'] = round(min(90, max(30, s['H'] + random.uniform(-1.5, 1.5))), 0)
                if random.random() < 0.03:
                    s['PLUIE'] = 1 - s['PLUIE']
                s['GAZ'] = 1 if random.random() < 0.01 else (s['GAZ'] if random.random() < 0.7 else 0)
                s['PIR'] = 1 if random.random() < 0.25 else 0
                s['FENETRE'] = 0 if s['PLUIE'] else 1
                if self._fan_mode == 'AUTO':
                    s['FAN'] = 1 if s['T'] >= TEMP_WARN else 0
                if random.random() < 0.02:
                    s['RFID'] = random.choice([1, 2])
                elif random.random() < 0.2:
                    s['RFID'] = 0
                s['GARAGE'] = 1 if s['RFID'] == 1 else 0
                self.last_update = time.time()

    def _simulate_command(self, command):
        with self._lock:
            key, _, value = command.partition(':')
            if key == 'PORTE':
                self.state['PORTE'] = 1 if value == 'OUVRIR' else 0
            elif key == 'FAN':
                self._fan_mode = 'AUTO' if value == 'AUTO' else 'MANUEL'
                if value in ('ON', 'OFF'):
                    self.state['FAN'] = 1 if value == 'ON' else 0
