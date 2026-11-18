"""Interface graphique Smart Home (remplace l'interface LabVIEW). Lancée par main.py."""
import argparse
import os
import time
from datetime import datetime

import customtkinter as ctk
from PIL import Image

from .camera import CameraWorker
from .config import (DOOR_AUTO_CLOSE_MS, ENROLL_SAMPLES, FACE_COOLDOWN_S,
                     NO_DATA_TIMEOUT_S, TEMP_ALERT, TEMP_WARN)
from .serial_link import SensorLink, available_ports

# ------------------------------------------------------------------ thème
BG = '#0b1120'
CARD = '#151d2e'
CARD_2 = '#1c2639'
BORDER = '#243049'
TEXT = '#e6ebf5'
MUTED = '#8a96ad'
ACCENT = '#3b82f6'
OK = '#22c55e'
WARN = '#f59e0b'
ALERT = '#ef4444'
OFF = '#475569'
LEVEL_COLORS = {'ok': OK, 'warn': WARN, 'alert': ALERT, 'off': OFF, 'info': ACCENT}

FONT = 'Segoe UI' if os.name == 'nt' else 'DejaVu Sans'


def font(size, weight='normal'):
    return ctk.CTkFont(family=FONT, size=size, weight=weight)


class Dot(ctk.CTkFrame):
    def __init__(self, master, size=10, color=OFF):
        super().__init__(master, width=size, height=size, corner_radius=size // 2,
                         fg_color=color)

    def set(self, color):
        self.configure(fg_color=color)


class Tile(ctk.CTkFrame):
    """Carte d'un capteur : titre, valeur, détail et pastille de couleur."""

    def __init__(self, master, title):
        super().__init__(master, fg_color=CARD, corner_radius=16, border_width=1,
                         border_color=BORDER)
        head = ctk.CTkFrame(self, fg_color='transparent')
        head.pack(fill='x', padx=16, pady=(14, 0))
        self.dot = Dot(head)
        self.dot.pack(side='left', padx=(0, 8))
        ctk.CTkLabel(head, text=title.upper(), font=font(11, 'bold'),
                     text_color=MUTED).pack(side='left')
        self.value = ctk.CTkLabel(self, text='--', font=font(24, 'bold'), text_color=TEXT,
                                  anchor='w')
        self.value.pack(fill='x', padx=16, pady=(6, 0))
        self.sub = ctk.CTkLabel(self, text='', font=font(12), text_color=MUTED, anchor='w')
        self.sub.pack(fill='x', padx=16, pady=(0, 14))

    def set(self, value, sub='', level='off'):
        color = LEVEL_COLORS[level]
        self.dot.set(color)
        self.value.configure(text=value, text_color=ALERT if level == 'alert' else TEXT)
        self.sub.configure(text=sub)
        self.configure(border_color=ALERT if level == 'alert' else BORDER)


class GaugeTile(Tile):
    """Carte avec une barre de niveau (température, humidité)."""

    def __init__(self, master, title, maximum):
        super().__init__(master, title)
        self.maximum = maximum
        self.sub.pack_forget()
        self.bar = ctk.CTkProgressBar(self, height=8, corner_radius=4, fg_color=CARD_2)
        self.bar.set(0)
        self.bar.pack(fill='x', padx=16, pady=(4, 0))
        self.sub.pack(fill='x', padx=16, pady=(4, 14))

    def set_value(self, number, text, sub, level):
        self.set(text, sub, level)
        self.bar.set(0 if number is None else max(0, min(1, number / self.maximum)))
        self.bar.configure(progress_color=LEVEL_COLORS[level])


class SmartHomeApp(ctk.CTk):
    def __init__(self, camera_source, start_simulation):
        super().__init__(fg_color=BG)
        self.title('Smart Home – Tableau de bord')
        self.geometry('1400x860')
        self.minsize(1200, 760)

        self.link = SensorLink(on_log=lambda msg: self.after(0, self.log, msg))
        self.camera = CameraWorker(camera_source)
        self.prev_state = {}
        self.last_face_open = 0.0
        self.close_job = None

        self.grid_columnconfigure(0, weight=5, uniform='col')
        self.grid_columnconfigure(1, weight=6, uniform='col')
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_camera_panel()
        self._build_sensor_panel()

        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.camera.start()
        self.log('Application démarrée')
        people = self.camera.known_people()
        self.log('Personnes reconnues : ' + (', '.join(people) if people else 'aucune'))
        if start_simulation:
            self.toggle_simulation()

        self.after(40, self.update_video)
        self.after(100, self.process_camera_events)
        self.after(300, self.update_sensors)
        self.after(1000, self.update_clock)

    # ================================================================ UI
    def _build_header(self):
        bar = ctk.CTkFrame(self, fg_color='transparent')
        bar.grid(row=0, column=0, columnspan=2, sticky='ew', padx=24, pady=(20, 12))

        logo = ctk.CTkFrame(bar, width=44, height=44, corner_radius=12, fg_color=ACCENT)
        logo.pack(side='left')
        logo.pack_propagate(False)
        ctk.CTkLabel(logo, text='⌂', font=font(24, 'bold'), text_color='white').pack(expand=True)

        titles = ctk.CTkFrame(bar, fg_color='transparent')
        titles.pack(side='left', padx=14)
        ctk.CTkLabel(titles, text='Smart Home', font=font(22, 'bold'), text_color=TEXT,
                     anchor='w').pack(fill='x')
        self.clock = ctk.CTkLabel(titles, text='', font=font(12), text_color=MUTED, anchor='w')
        self.clock.pack(fill='x')
        self.update_clock(schedule=False)

        right = ctk.CTkFrame(bar, fg_color='transparent')
        right.pack(side='right')

        pill = ctk.CTkFrame(right, fg_color=CARD, corner_radius=18, border_width=1,
                            border_color=BORDER)
        pill.pack(side='left', padx=(0, 14))
        self.status_dot = Dot(pill, color=OFF)
        self.status_dot.pack(side='left', padx=(14, 8), pady=10)
        self.status_text = ctk.CTkLabel(pill, text='Déconnecté', font=font(13), text_color=TEXT)
        self.status_text.pack(side='left', padx=(0, 14))

        self.port_box = ctk.CTkComboBox(right, width=150, height=36, values=['Aucun port'],
                                        font=font(13), fg_color=CARD, border_color=BORDER,
                                        button_color=CARD_2, dropdown_fg_color=CARD)
        self.port_box.pack(side='left', padx=(0, 6))
        ctk.CTkButton(right, text='↻', width=36, height=36, font=font(16), fg_color=CARD_2,
                      hover_color=BORDER, command=self.refresh_ports).pack(side='left', padx=(0, 10))
        self.connect_btn = ctk.CTkButton(right, text='Connecter', width=120, height=36,
                                         font=font(13, 'bold'), fg_color=ACCENT,
                                         command=self.toggle_connection)
        self.connect_btn.pack(side='left', padx=(0, 8))
        self.sim_btn = ctk.CTkButton(right, text='Simulation', width=120, height=36,
                                     font=font(13), fg_color=CARD_2, hover_color=BORDER,
                                     command=self.toggle_simulation)
        self.sim_btn.pack(side='left')
        self.refresh_ports()

    def _build_camera_panel(self):
        panel = ctk.CTkFrame(self, fg_color=CARD, corner_radius=20, border_width=1,
                             border_color=BORDER)
        panel.grid(row=1, column=0, sticky='nsew', padx=(24, 10), pady=(0, 24))
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(panel, fg_color='transparent')
        head.grid(row=0, column=0, sticky='ew', padx=20, pady=(18, 10))
        ctk.CTkLabel(head, text='Caméra · Reconnaissance faciale', font=font(16, 'bold'),
                     text_color=TEXT).pack(side='left')
        self.live_dot = Dot(head, 8, OFF)
        self.live_dot.pack(side='right', padx=(6, 0))
        self.live_text = ctk.CTkLabel(head, text='HORS LIGNE', font=font(11, 'bold'),
                                      text_color=MUTED)
        self.live_text.pack(side='right')

        self.video_holder = ctk.CTkFrame(panel, fg_color='#05080f', corner_radius=14)
        self.video_holder.grid(row=1, column=0, sticky='nsew', padx=20)
        self.video = ctk.CTkLabel(self.video_holder, text='Démarrage de la caméra...',
                                  font=font(14), text_color=MUTED)
        self.video.pack(expand=True, fill='both', padx=4, pady=4)

        self.banner = ctk.CTkFrame(panel, fg_color=CARD_2, corner_radius=14)
        self.banner.grid(row=2, column=0, sticky='ew', padx=20, pady=(14, 0))
        self.banner_title = ctk.CTkLabel(self.banner, text='Aucun visage détecté',
                                         font=font(18, 'bold'), text_color=TEXT, anchor='w')
        self.banner_title.pack(fill='x', padx=18, pady=(12, 0))
        self.banner_sub = ctk.CTkLabel(self.banner, text='Placez-vous devant la caméra',
                                       font=font(12), text_color=MUTED, anchor='w')
        self.banner_sub.pack(fill='x', padx=18, pady=(0, 12))

        actions = ctk.CTkFrame(panel, fg_color='transparent')
        actions.grid(row=3, column=0, sticky='ew', padx=20, pady=(14, 18))
        actions.grid_columnconfigure(1, weight=1)
        self.enroll_btn = ctk.CTkButton(actions, text='+  Ajouter mon visage', height=40,
                                        font=font(14, 'bold'), fg_color=ACCENT,
                                        command=self.ask_enroll)
        self.enroll_btn.grid(row=0, column=0, rowspan=2, padx=(0, 16))
        self.people_label = ctk.CTkLabel(actions, text='', font=font(12), text_color=MUTED,
                                         anchor='w')
        self.people_label.grid(row=0, column=1, sticky='ew')
        self.enroll_bar = ctk.CTkProgressBar(actions, height=8, fg_color=CARD_2,
                                             progress_color=ACCENT)
        self.enroll_bar.set(0)
        self.enroll_bar.grid(row=1, column=1, sticky='ew', pady=(6, 0))
        self.enroll_bar.grid_remove()       # visible seulement pendant l'ajout
        self.update_people()

    def _build_sensor_panel(self):
        panel = ctk.CTkFrame(self, fg_color='transparent')
        panel.grid(row=1, column=1, sticky='nsew', padx=(10, 24), pady=(0, 24))
        for c in range(4):
            panel.grid_columnconfigure(c, weight=1, uniform='tile')
        panel.grid_rowconfigure(3, weight=1)
        pad = dict(padx=6, pady=6, sticky='nsew')

        self.t_temp = GaugeTile(panel, 'Température', 50)
        self.t_hum = GaugeTile(panel, 'Humidité', 100)
        self.t_gas = Tile(panel, 'Gaz / Fumée')
        self.t_rain = Tile(panel, 'Pluie')
        self.t_pir = Tile(panel, 'Mouvement')
        self.t_rfid = Tile(panel, 'Badge RFID')
        self.t_window = Tile(panel, 'Fenêtre')
        self.t_garage = Tile(panel, 'Garage')
        tiles = [self.t_temp, self.t_hum, self.t_gas, self.t_rain,
                 self.t_pir, self.t_rfid, self.t_window, self.t_garage]
        for i, t in enumerate(tiles):
            t.grid(row=i // 4, column=i % 4, **pad)

        # --- Ventilateur
        fan = ctk.CTkFrame(panel, fg_color=CARD, corner_radius=16, border_width=1,
                           border_color=BORDER)
        fan.grid(row=2, column=0, columnspan=2, **pad)
        self.t_fan_dot, self.t_fan_value = self._control_header(fan, 'Ventilateur')
        self.fan_mode = ctk.CTkSegmentedButton(
            fan, values=['Auto', 'Marche', 'Arrêt'], font=font(13), height=34,
            fg_color=CARD_2, selected_color=ACCENT, unselected_color=CARD_2,
            command=self.set_fan_mode)
        self.fan_mode.set('Auto')
        self.fan_mode.pack(fill='x', padx=16, pady=(4, 16))

        # --- Porte principale
        door = ctk.CTkFrame(panel, fg_color=CARD, corner_radius=16, border_width=1,
                            border_color=BORDER)
        door.grid(row=2, column=2, columnspan=2, **pad)
        self.t_door_dot, self.t_door_value = self._control_header(door, 'Porte principale')
        row = ctk.CTkFrame(door, fg_color='transparent')
        row.pack(fill='x', padx=16, pady=(4, 6))
        ctk.CTkButton(row, text='Ouvrir', height=34, font=font(13, 'bold'), fg_color=OK,
                      hover_color='#16a34a', command=lambda: self.door('OUVRIR')
                      ).pack(side='left', expand=True, fill='x', padx=(0, 4))
        ctk.CTkButton(row, text='Fermer', height=34, font=font(13, 'bold'), fg_color=CARD_2,
                      hover_color=BORDER, command=lambda: self.door('FERMER')
                      ).pack(side='left', expand=True, fill='x', padx=(4, 0))
        self.face_auto = ctk.CTkSwitch(door, text='Ouverture auto par reconnaissance faciale',
                                       font=font(12), text_color=MUTED, progress_color=ACCENT)
        self.face_auto.select()
        self.face_auto.pack(anchor='w', padx=16, pady=(4, 14))

        # --- Journal
        log_card = ctk.CTkFrame(panel, fg_color=CARD, corner_radius=16, border_width=1,
                                border_color=BORDER)
        log_card.grid(row=3, column=0, columnspan=4, **pad)
        ctk.CTkLabel(log_card, text='JOURNAL DES ÉVÉNEMENTS', font=font(11, 'bold'),
                     text_color=MUTED, anchor='w').pack(fill='x', padx=16, pady=(14, 4))
        self.log_box = ctk.CTkTextbox(log_card, font=ctk.CTkFont(family='Consolas' if os.name == 'nt'
                                                                  else 'DejaVu Sans Mono', size=12),
                                      fg_color=CARD, text_color=TEXT, wrap='word',
                                      activate_scrollbars=True)
        self.log_box.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        self.log_box.tag_config('time', foreground=MUTED)
        self.log_box.tag_config('alert', foreground=ALERT)
        self.log_box.tag_config('ok', foreground=OK)
        self.log_box.configure(state='disabled')

    def _control_header(self, parent, title):
        head = ctk.CTkFrame(parent, fg_color='transparent')
        head.pack(fill='x', padx=16, pady=(14, 0))
        dot = Dot(head)
        dot.pack(side='left', padx=(0, 8))
        ctk.CTkLabel(head, text=title.upper(), font=font(11, 'bold'),
                     text_color=MUTED).pack(side='left')
        value = ctk.CTkLabel(parent, text='--', font=font(22, 'bold'), text_color=TEXT,
                             anchor='w')
        value.pack(fill='x', padx=16, pady=(4, 4))
        return dot, value

    # ========================================================== actions
    def log(self, message, kind=None):
        self.log_box.configure(state='normal')
        self.log_box.insert('end', datetime.now().strftime('%H:%M:%S  '), 'time')
        self.log_box.insert('end', message + '\n', kind or ())
        lines = int(self.log_box.index('end-1c').split('.')[0])
        if lines > 300:
            self.log_box.delete('1.0', f'{lines - 300}.0')
        self.log_box.see('end')
        self.log_box.configure(state='disabled')

    def refresh_ports(self):
        ports = available_ports()
        self.port_box.configure(values=ports or ['Aucun port'])
        self.port_box.set(ports[0] if ports else 'Aucun port')

    def toggle_connection(self):
        if self.link.mode == 'serial':
            self.link.disconnect()
        else:
            port = self.port_box.get()
            if not port or port == 'Aucun port':
                self.log('Aucun port série trouvé. Branchez l\'Arduino puis cliquez sur ↻',
                         'alert')
                return
            try:
                self.link.connect(port)
            except Exception as e:
                self.log(f'Connexion impossible : {e}', 'alert')
        self.update_mode_buttons()

    def toggle_simulation(self):
        if self.link.mode == 'simulation':
            self.link.disconnect()
        else:
            self.link.start_simulation()
        self.update_mode_buttons()

    def update_mode_buttons(self):
        mode = self.link.mode
        self.connect_btn.configure(text='Déconnecter' if mode == 'serial' else 'Connecter',
                                   fg_color=ALERT if mode == 'serial' else ACCENT)
        self.sim_btn.configure(text='Arrêter simulation' if mode == 'simulation'
                               else 'Simulation',
                               fg_color=WARN if mode == 'simulation' else CARD_2,
                               text_color='#111' if mode == 'simulation' else TEXT)

    def set_fan_mode(self, value):
        self.link.send({'Auto': 'FAN:AUTO', 'Marche': 'FAN:ON', 'Arrêt': 'FAN:OFF'}[value])

    def door(self, action):
        self.link.send(f'PORTE:{action}')
        if self.close_job:
            self.after_cancel(self.close_job)
            self.close_job = None
        if action == 'OUVRIR':
            self.close_job = self.after(DOOR_AUTO_CLOSE_MS, lambda: self.door('FERMER'))

    def ask_enroll(self):
        if self.camera.is_busy():
            return
        dialog = ctk.CTkInputDialog(title='Ajouter mon visage',
                                    text='Votre prénom (lettres et chiffres) :')
        name = dialog.get_input()
        if not name:
            return
        try:
            name = self.camera.start_enroll(name)
        except Exception as e:
            self.log(str(e), 'alert')
            return
        self.enroll_btn.configure(state='disabled', text='Capture en cours...')
        self.enroll_bar.set(0)
        self.enroll_bar.grid()
        self.people_label.configure(text=f'Regardez la caméra, {name}. Bougez un peu la tête '
                                         '(gauche, droite, haut, bas).', text_color=TEXT)
        self.log(f'Ajout du visage de « {name} » : {ENROLL_SAMPLES} photos à prendre')

    def update_people(self):
        people = self.camera.known_people()
        self.people_label.configure(
            text='Personnes enregistrées : ' + (', '.join(people) if people else 'aucune'),
            text_color=MUTED)

    def on_close(self):
        self.camera.stop()
        self.link.disconnect()
        self.destroy()

    # ===================================================== mises à jour
    def update_clock(self, schedule=True):
        days = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
        now = datetime.now()
        self.clock.configure(text=f'{days[now.weekday()].capitalize()} '
                                  f'{now:%d/%m/%Y · %H:%M:%S}')
        if schedule:
            self.after(1000, self.update_clock)

    def update_video(self):
        frame = self.camera.latest_frame
        if frame is not None:
            w = max(self.video_holder.winfo_width() - 8, 100)
            h = max(self.video_holder.winfo_height() - 8, 100)
            fh, fw = frame.shape[:2]
            scale = min(w / fw, h / fh)
            size = (int(fw * scale), int(fh * scale))
            img = Image.fromarray(frame[:, :, ::-1])
            self.video.configure(image=ctk.CTkImage(img, size=size), text='')
            self.live_dot.set(ALERT)
            self.live_text.configure(text='EN DIRECT', text_color=TEXT)
        self.after(40, self.update_video)

    def process_camera_events(self):
        while not self.camera.events.empty():
            event = self.camera.events.get()
            kind = event[0]
            if kind == 'person':
                self.on_person(event[1])
            elif kind == 'enroll':
                _, n, total = event
                self.enroll_bar.set(n / total)
            elif kind == 'training':
                self.enroll_btn.configure(text='Entraînement...')
                self.people_label.configure(text='Entraînement du modèle, patientez...')
                self.enroll_bar.configure(mode='indeterminate')
                self.enroll_bar.start()
            elif kind == 'trained':
                _, name, score = event
                self.enroll_bar.stop()
                self.enroll_bar.configure(mode='determinate')
                self.enroll_bar.grid_remove()
                self.enroll_btn.configure(state='normal', text='+  Ajouter mon visage')
                self.update_people()
                self.log(f'Visage de « {name} » ajouté. Précision du modèle : {score:.0%}', 'ok')
            elif kind == 'saved':
                self.enroll_bar.stop()
                self.enroll_bar.configure(mode='determinate')
                self.enroll_bar.grid_remove()
                self.enroll_btn.configure(state='normal', text='+  Ajouter mon visage')
                self.update_people()
                self.log(f'Visage de « {event[1]} » enregistré. Ajoutez une 2e personne pour '
                         'activer la reconnaissance.', 'ok')
            elif kind == 'error':
                self.enroll_bar.stop()
                self.enroll_bar.configure(mode='determinate')
                self.enroll_bar.grid_remove()
                self.enroll_btn.configure(state='normal', text='+  Ajouter mon visage')
                self.update_people()
                self.video.configure(text=event[1])
                self.log(event[1], 'alert')
        self.after(100, self.process_camera_events)

    def on_person(self, name):
        if name == '':
            self.set_banner(CARD_2, 'Aucun visage détecté', 'Placez-vous devant la caméra')
        elif name is None:
            self.set_banner('#3b1219', 'Visage inconnu', 'Accès refusé', ALERT)
            self.log('Visage inconnu détecté devant la caméra', 'alert')
            self.link.send('VISAGE:INCONNU')
        else:
            self.set_banner('#0f2e1d', f'Bienvenue, {name.capitalize()} !', 'Accès autorisé', OK)
            self.log(f'{name.capitalize()} reconnu(e)', 'ok')
            if self.face_auto.get() and time.time() - self.last_face_open > FACE_COOLDOWN_S:
                self.last_face_open = time.time()
                self.link.send(f'VISAGE:{name}')
                self.door('OUVRIR')

    def set_banner(self, bg, title, sub, accent=None):
        self.banner.configure(fg_color=bg)
        self.banner_title.configure(text=title, text_color=accent or TEXT)
        self.banner_sub.configure(text=sub)

    def update_sensors(self):
        s, last = self.link.snapshot()
        mode = self.link.mode
        stale = mode and time.time() - last > NO_DATA_TIMEOUT_S

        if mode is None:
            self.status_dot.set(OFF)
            self.status_text.configure(text='Déconnecté')
        elif stale:
            self.status_dot.set(WARN)
            self.status_text.configure(text='En attente de données...')
        else:
            self.status_dot.set(WARN if mode == 'simulation' else OK)
            self.status_text.configure(text='Simulation' if mode == 'simulation'
                                       else 'Arduino connecté')

        if mode is None or s['T'] is None:
            for t in (self.t_temp, self.t_hum):
                t.set_value(None, '--', 'Pas de données', 'off')
        else:
            t = s['T']
            lvl = 'alert' if t >= TEMP_ALERT else 'warn' if t >= TEMP_WARN else 'ok'
            self.t_temp.set_value(t, f'{t:.1f} °C',
                                  'Chaud – ventilation conseillée' if t >= TEMP_WARN else 'Confortable',
                                  lvl)
            h = s['H']
            lvl = 'warn' if h > 70 or h < 30 else 'info'
            self.t_hum.set_value(h, f'{h:.0f} %', 'Air humide' if h > 70 else
                                 'Air sec' if h < 30 else 'Normale', lvl)

        live = mode is not None
        self.t_gas.set(*(('DANGER', 'Gaz détecté ! Alarme activée', 'alert') if s['GAZ']
                         else ('Normal', 'Aucun gaz détecté', 'ok')) if live else ('--', '', 'off'))
        self.t_rain.set(*(('Pluie', 'Fenêtres fermées', 'info') if s['PLUIE']
                          else ('Sec', 'Pas de pluie', 'ok')) if live else ('--', '', 'off'))
        self.t_pir.set(*(('Détecté', 'Présence détectée', 'warn') if s['PIR']
                         else ('Aucun', 'Pas de mouvement', 'off')) if live else ('--', '', 'off'))
        rfid = {0: ('En attente', 'Présentez un badge', 'off'),
                1: ('Autorisé', 'Badge valide', 'ok'),
                2: ('Refusé', 'Badge non autorisé', 'alert')}
        self.t_rfid.set(*rfid.get(s['RFID'], rfid[0]) if live else ('--', '', 'off'))
        self.t_window.set(*(('Ouverte', 'Aération', 'info') if s['FENETRE']
                            else ('Fermée', '', 'off')) if live else ('--', '', 'off'))
        self.t_garage.set(*(('Ouvert', '', 'warn') if s['GARAGE']
                            else ('Fermé', '', 'off')) if live else ('--', '', 'off'))

        self.t_fan_dot.set(OK if live and s['FAN'] else OFF)
        self.t_fan_value.configure(text=('En marche' if s['FAN'] else 'Arrêté') if live else '--')
        self.t_door_dot.set(OK if live and s['PORTE'] else OFF)
        self.t_door_value.configure(text=('Ouverte' if s['PORTE'] else 'Fermée') if live else '--')

        if live:
            self.log_changes(s)
        self.prev_state = s if live else {}
        self.after(300, self.update_sensors)

    def log_changes(self, s):
        p = self.prev_state
        if not p:
            return
        if s['GAZ'] and not p.get('GAZ'):
            self.log('ALERTE : gaz / fumée détecté !', 'alert')
        if s['PLUIE'] != p.get('PLUIE'):
            self.log('Pluie détectée – fenêtres fermées' if s['PLUIE'] else 'Fin de la pluie')
        if s['FAN'] != p.get('FAN'):
            self.log('Ventilateur en marche' if s['FAN'] else 'Ventilateur arrêté')
        if s['PORTE'] != p.get('PORTE'):
            self.log('Porte ouverte' if s['PORTE'] else 'Porte fermée')
        if s['RFID'] != p.get('RFID') and s['RFID'] in (1, 2):
            self.log('Badge RFID autorisé' if s['RFID'] == 1 else 'Badge RFID refusé',
                     'ok' if s['RFID'] == 1 else 'alert')

