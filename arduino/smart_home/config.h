/*
 * config.h — Réglages de la maison intelligente (Arduino Mega 2560)
 * Les broches reprennent le tableau du rapport (chapitre 3).
 */
#ifndef CONFIG_H
#define CONFIG_H

// ------------------------------------------------------------ Capteurs
#define PIN_GAZ          5    // MQ2 (sortie numérique DO)
#define PIN_PLUIE        2    // capteur de pluie (sortie numérique DO)
#define PIN_DHT          A0   // DHT11 (broche 54 = A0)
#define PIN_PIR          7    // capteur de mouvement

// Module RFID RC522 (bus SPI). Sur la Mega, le SPI matériel est sur
// 50 (MISO), 51 (MOSI), 52 (SCK), 53 (SS) — et non 11/12/13 comme sur l'Uno.
#define PIN_RFID_SS      53
#define PIN_RFID_RST     49   // le rapport indiquait 5, déjà utilisée par le MQ2

// ---------------------------------------------------------- Actionneurs
#define PIN_BUZZER       6
#define PIN_LED          8    // s'allume quand un mouvement est détecté
#define PIN_SERVO_FENETRE  9
#define PIN_SERVO_VENTIL   3
#define PIN_SERVO_PORTE    10
#define PIN_SERVO_GARAGE   4
// Écran LCD I2C 16x2 : SDA = 20, SCL = 21 (fixe sur la Mega)
#define LCD_ADRESSE      0x27 // essayez 0x3F si l'écran reste vide

// ----------------------------------------------- Logique des capteurs
// La plupart des modules MQ2 et pluie mettent DO à LOW quand ils détectent.
#define GAZ_DETECTE      LOW
#define PLUIE_DETECTEE   LOW

// ------------------------------------------------------ Angles servos
#define FENETRE_OUVERTE  90
#define FENETRE_FERMEE   0
#define PORTE_OUVERTE    90
#define PORTE_FERMEE     0
#define GARAGE_OUVERT    90
#define GARAGE_FERME     0

// --------------------------------------------------------------- Seuils
#define SEUIL_TEMPERATURE   30.0  // °C : le ventilateur démarre
#define HYSTERESIS_TEMP     1.0   // il s'arrête sous 29 °C (évite les clignotements)

// ------------------------------------------------------------- Durées
#define DUREE_GARAGE_MS      5000UL   // garage ouvert après un badge valide
#define DUREE_PORTE_MAX_MS   20000UL  // sécurité : la porte se referme toute seule
#define DUREE_MESSAGE_MS     3000UL   // messages temporaires sur le LCD
#define PERIODE_DHT_MS       2000UL   // le DHT11 ne supporte pas plus rapide
#define PERIODE_ENVOI_MS     500UL    // envoi de l'état au PC
#define PERIODE_LCD_MS       1000UL

// --------------------------------------------------- Badges autorisés
// UID affiché dans le moniteur série quand on passe un badge.
const byte BADGES_AUTORISES[][4] = {
  {0xF3, 0x7E, 0x59, 0x1A},   // badge du rapport (figure 34)
};

#define VITESSE_SERIE    9600  // identique à BAUDRATE dans python/smarthome/config.py

#endif
