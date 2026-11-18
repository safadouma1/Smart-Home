/*
 * smart_home.ino — Maison intelligente (Arduino Mega 2560)
 *
 *  Salon   : DHT11 -> écran LCD + ventilateur automatique au-dessus de 30 °C
 *  Cuisine : MQ2 -> buzzer + alerte
 *  Fenêtre : se ferme automatiquement quand il pleut
 *  Couloir : PIR -> LED
 *  Garage  : s'ouvre avec un badge RFID autorisé
 *  Porte   : ouverte par l'application Python (reconnaissance faciale)
 *
 * Communication avec l'application (USB, 9600 bauds) :
 *  Arduino -> PC : T:25.3;H:60;GAZ:0;PLUIE:0;PIR:1;FAN:0;PORTE:0;FENETRE:1;GARAGE:0;RFID:0
 *  PC -> Arduino : PORTE:OUVRIR | PORTE:FERMER | FAN:ON | FAN:OFF | FAN:AUTO
 *                  VISAGE:<nom> | VISAGE:INCONNU
 *
 * Bibliothèques à installer (Arduino IDE > Outils > Gérer les bibliothèques) :
 *  - "DHT sensor library" (Adafruit) + "Adafruit Unified Sensor"
 *  - "LiquidCrystal I2C" (Frank de Brabander)
 *  - "MFRC522" (GithubCommunity / miguelbalboa)
 *  Servo, Wire et SPI sont déjà inclus dans l'IDE.
 */
#include <Wire.h>
#include <SPI.h>
#include <Servo.h>
#include <DHT.h>
#include <LiquidCrystal_I2C.h>
#include <MFRC522.h>
#include "config.h"

DHT dht(PIN_DHT, DHT11);
LiquidCrystal_I2C lcd(LCD_ADRESSE, 16, 2);
MFRC522 rfid(PIN_RFID_SS, PIN_RFID_RST);
Servo servoFenetre, servoVentil, servoPorte, servoGarage;

// ------------------------------------------------------------- État
float temperature = NAN, humidite = NAN;
bool gaz = false, pluie = false, mouvement = false;
bool ventilateur = false, ventilateurAuto = true;
bool porte = false, fenetre = true, garage = false;
byte etatRfid = 0;                    // 0 aucun, 1 autorisé, 2 refusé

unsigned long tDht = 0, tEnvoi = 0, tLcd = 0;
unsigned long tGarage = 0, tPorte = 0, tRfid = 0, tMessage = 0;
unsigned long tBuzzer = 0, tVentil = 0;
int angleVentil = 0, sensVentil = 3;
String commande = "";

// ============================================================ Outils
void bip(unsigned int ms) {           // bip court sans bloquer
  digitalWrite(PIN_BUZZER, HIGH);
  tBuzzer = millis() + ms;
}

void afficherMessage(const String &ligne1, const String &ligne2) {
  lcd.clear();
  lcd.setCursor(0, 0); lcd.print(ligne1.substring(0, 16));
  lcd.setCursor(0, 1); lcd.print(ligne2.substring(0, 16));
  tMessage = millis();
}

// ======================================================= Actionneurs
void ouvrirPorte()  { servoPorte.write(PORTE_OUVERTE); porte = true; tPorte = millis(); }
void fermerPorte()  { servoPorte.write(PORTE_FERMEE);  porte = false; }
void ouvrirGarage() { servoGarage.write(GARAGE_OUVERT); garage = true; tGarage = millis(); }
void fermerGarage() { servoGarage.write(GARAGE_FERME);  garage = false; }

void ouvrirFenetre(bool ouvrir) {
  if (ouvrir == fenetre) return;
  servoFenetre.write(ouvrir ? FENETRE_OUVERTE : FENETRE_FERMEE);
  fenetre = ouvrir;
}

// Le ventilateur est un servo qui balaye de 0 à 180° tant qu'il est en marche.
void gererVentilateur() {
  if (ventilateurAuto && !isnan(temperature)) {
    if (temperature >= SEUIL_TEMPERATURE) ventilateur = true;
    else if (temperature < SEUIL_TEMPERATURE - HYSTERESIS_TEMP) ventilateur = false;
  }
  if (ventilateur && millis() - tVentil >= 15) {
    tVentil = millis();
    angleVentil += sensVentil;
    if (angleVentil >= 180 || angleVentil <= 0) sensVentil = -sensVentil;
    angleVentil = constrain(angleVentil, 0, 180);
    servoVentil.write(angleVentil);
  }
}

// ========================================================== Capteurs
void lireCapteurs() {
  bool gazAvant = gaz;
  gaz = digitalRead(PIN_GAZ) == GAZ_DETECTE;
  pluie = digitalRead(PIN_PLUIE) == PLUIE_DETECTEE;
  mouvement = digitalRead(PIN_PIR) == HIGH;

  digitalWrite(PIN_LED, mouvement ? HIGH : LOW);
  ouvrirFenetre(!pluie);                       // pluie -> fenêtre fermée

  if (gaz && !gazAvant) afficherMessage("!! ALERTE GAZ !!", "Aerez la maison");

  if (millis() - tDht >= PERIODE_DHT_MS) {
    tDht = millis();
    float t = dht.readTemperature();
    float h = dht.readHumidity();
    if (!isnan(t)) temperature = t;
    if (!isnan(h)) humidite = h;
  }
}

bool badgeAutorise(const MFRC522::Uid &uid) {
  for (byte b = 0; b < sizeof(BADGES_AUTORISES) / sizeof(BADGES_AUTORISES[0]); b++) {
    if (uid.size != 4) return false;
    bool identique = true;
    for (byte i = 0; i < 4; i++)
      if (uid.uidByte[i] != BADGES_AUTORISES[b][i]) identique = false;
    if (identique) return true;
  }
  return false;
}

void lireBadge() {
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;

  // Afficher l'UID dans le moniteur série (pour ajouter un badge dans config.h)
  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(rfid.uid.uidByte[i], HEX);
    if (i < rfid.uid.size - 1) uid += " ";
  }
  uid.toUpperCase();
  Serial.print("# Badge UID: ");
  Serial.println(uid);

  if (badgeAutorise(rfid.uid)) {
    etatRfid = 1;
    ouvrirGarage();
    afficherMessage("Card: " + uid, "Access Granted");
    bip(100);
  } else {
    etatRfid = 2;
    afficherMessage("Card: " + uid, "Access Denied");
    bip(600);
  }
  tRfid = millis();
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
}

// ===================================================== Communication
void envoyerEtat() {
  Serial.print("T:");        Serial.print(isnan(temperature) ? 0 : temperature, 1);
  Serial.print(";H:");       Serial.print(isnan(humidite) ? 0 : humidite, 0);
  Serial.print(";GAZ:");     Serial.print(gaz);
  Serial.print(";PLUIE:");   Serial.print(pluie);
  Serial.print(";PIR:");     Serial.print(mouvement);
  Serial.print(";FAN:");     Serial.print(ventilateur);
  Serial.print(";PORTE:");   Serial.print(porte);
  Serial.print(";FENETRE:"); Serial.print(fenetre);
  Serial.print(";GARAGE:");  Serial.print(garage);
  Serial.print(";RFID:");    Serial.println(etatRfid);
}

void executerCommande(String cmd) {
  cmd.trim();
  if (cmd == "PORTE:OUVRIR")       ouvrirPorte();
  else if (cmd == "PORTE:FERMER")  fermerPorte();
  else if (cmd == "FAN:ON")   { ventilateurAuto = false; ventilateur = true; }
  else if (cmd == "FAN:OFF")  { ventilateurAuto = false; ventilateur = false; }
  else if (cmd == "FAN:AUTO")   ventilateurAuto = true;
  else if (cmd == "VISAGE:INCONNU") {
    afficherMessage("Visage inconnu", "Acces refuse");
    bip(600);
  } else if (cmd.startsWith("VISAGE:")) {
    afficherMessage("Bienvenue", cmd.substring(7));
    bip(100);
  }
}

void lireCommandes() {                 // lecture sans bloquer, ligne par ligne
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      executerCommande(commande);
      commande = "";
    } else if (c != '\r' && commande.length() < 40) {
      commande += c;
    }
  }
}

// ============================================================ Écran
void mettreAJourLcd() {
  if (millis() - tMessage < DUREE_MESSAGE_MS) return;   // message en cours
  if (millis() - tLcd < PERIODE_LCD_MS) return;
  tLcd = millis();

  lcd.setCursor(0, 0);
  if (isnan(temperature)) lcd.print("Temp: --        ");
  else { lcd.print("Temp: "); lcd.print(temperature, 2); lcd.print(" C    "); }

  lcd.setCursor(0, 1);
  if (gaz)        lcd.print("!! GAZ DETECTE !");
  else if (pluie) lcd.print("Rain            ");
  else            lcd.print("No Rain         ");
}

// ============================================================ Setup
void setup() {
  Serial.begin(VITESSE_SERIE);

  pinMode(PIN_GAZ, INPUT);
  pinMode(PIN_PLUIE, INPUT);
  pinMode(PIN_PIR, INPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_LED, OUTPUT);

  servoFenetre.attach(PIN_SERVO_FENETRE);
  servoVentil.attach(PIN_SERVO_VENTIL);
  servoPorte.attach(PIN_SERVO_PORTE);
  servoGarage.attach(PIN_SERVO_GARAGE);
  servoFenetre.write(FENETRE_OUVERTE);
  servoVentil.write(0);
  fermerPorte();
  fermerGarage();

  dht.begin();
  SPI.begin();
  rfid.PCD_Init();

  lcd.init();
  lcd.backlight();
  afficherMessage("  Smart Home", "  Demarrage...");
}

// ============================================================= Loop
void loop() {
  unsigned long now = millis();

  lireCommandes();
  lireCapteurs();
  lireBadge();
  gererVentilateur();

  // Buzzer : continu tant qu'il y a du gaz, sinon bips courts
  if (gaz) digitalWrite(PIN_BUZZER, HIGH);
  else if (now >= tBuzzer) digitalWrite(PIN_BUZZER, LOW);

  // Fermetures automatiques
  if (garage && now - tGarage >= DUREE_GARAGE_MS) fermerGarage();
  if (porte && now - tPorte >= DUREE_PORTE_MAX_MS) fermerPorte();
  if (etatRfid != 0 && now - tRfid >= DUREE_MESSAGE_MS) etatRfid = 0;

  mettreAJourLcd();

  if (now - tEnvoi >= PERIODE_ENVOI_MS) {
    tEnvoi = now;
    envoyerEtat();
  }
}
