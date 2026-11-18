"""Point d'entrée : lance le tableau de bord Smart Home.

    python main.py                  webcam 0
    python main.py --camera 1       autre webcam
    python main.py --simulation     démarrer sans Arduino (valeurs fictives)
    python main.py --video f.mp4    tester avec une vidéo au lieu de la webcam
"""
import argparse

import customtkinter as ctk

from smarthome.config import CAMERA_INDEX
from smarthome.interface import SmartHomeApp


def main():
    parser = argparse.ArgumentParser(description='Smart Home – tableau de bord')
    parser.add_argument('--camera', type=int, default=CAMERA_INDEX, help='numéro de la webcam')
    parser.add_argument('--video', help='fichier vidéo à utiliser à la place de la webcam')
    parser.add_argument('--simulation', action='store_true', help='démarrer en simulation')
    args = parser.parse_args()

    ctk.set_appearance_mode('dark')
    ctk.set_default_color_theme('blue')
    app = SmartHomeApp(args.video or args.camera, args.simulation)
    app.mainloop()


if __name__ == '__main__':
    main()
