# Satellite vocal ESP32-S3

Un satellite vocal Home Assistant entierement local, construit autour d'un ESP32-S3 avec ecran LCD rond, anneau LED et un boitier imprime en 3D incline — le tout configure sous ESPHome.

## Materiel

### Liste des composants

| Composant | Reference | Lien | Notes |
|---|---|---|---|
| MCU | ESP32-S3-DevKitC-1 | [AliExpress](https://www.aliexpress.com/item/1005008796158734.html) | Doit avoir une PSRAM octale (pour le wake word local) |
| Microphone | INMP441 (module MH-ET LIVE) | [AliExpress](https://www.aliexpress.com/item/1005006109471759.html) | Micro MEMS I2S omnidirectionnel, canal gauche |
| Amplificateur | MAX98357A | [AliExpress](https://www.aliexpress.com/item/1005007003802663.html) | Ampli I2S Class-D mono 3W |
| Haut-parleur | 40 mm full-range | [AliExpress](https://www.aliexpress.com/item/1005010726060483.html) | Encastre en press-fit dans la base |
| Anneau LED | WS2812B, 12 LEDs | [AliExpress](https://www.aliexpress.com/item/1005009796023642.html) | ~50 mm de diametre externe |
| Ecran | GC9A01A, 1.28" rond | [AliExpress](https://www.aliexpress.com/item/1005004482028005.html) | 240x240, SPI, IPS |
| Visserie | 3x vis M3x8 fraisees | — | + 3x inserts M3 a chaud pour le corps |
| Cable | USB-C | — | Alimentation et premier flash |

### Cablage

```
Brochage GPIO ESP32-S3
────────────────────────────────────────────

Microphone INMP441 (bus I2S "i2s_mic")
  BCLK ─── GPIO1
  LRCLK ── GPIO2
  DOUT ─── GPIO4
  L/R ──── GND  (canal gauche)

Amplificateur MAX98357A (bus I2S "i2s_spk")
  BCLK ─── GPIO5
  LRCLK ── GPIO6
  DIN ──── GPIO7
  SD ───── GPIO8  (enable/shutdown, actif haut)

Anneau LED WS2812B
  DIN ──── GPIO15

Ecran rond GC9A01A (SPI)
  CLK ──── GPIO12
  MOSI ─── GPIO11
  CS ───── GPIO10
  DC ───── GPIO13
  RST ──── GPIO14

Alimentation
  3V3 ──── INMP441 VDD, GC9A01A VCC, anneau LED VCC
  5V ───── MAX98357A VIN
  GND ──── tous les GND
```

## Logiciel

Le firmware est un unique fichier YAML ESPHome : [`satellite.yaml`](satellite.yaml).

### Fonctionnalites

- **Wake word local** — utilise Micro Wake Word (`okay_nabu`) directement sur la PSRAM de l'ESP32-S3. Aucun flux audio ne quitte l'appareil tant que le mot de reveil n'est pas detecte.
- **Pipeline vocal** — transmet l'audio a Home Assistant pour la reconnaissance vocale (STT), le traitement d'intentions et la synthese vocale (TTS). Les reponses sont jouees via le MAX98357A.
- **Ecran rond anime** — rendu lambda personnalise a 10 fps :
  - Horloge numerique (heures, minutes, secondes) synchronisee avec Home Assistant
  - Affichage de la date (en francais) au repos
  - Trois anneaux d'arcs rotatifs concentriques a vitesses independantes
  - Indicateur de secondes fluide sur l'anneau exterieur
  - Anneau d'etat pulsant qui change de couleur selon l'etat de l'assistant vocal
  - Indicateur de volume avec icone haut-parleur
  - Indicateur de signal WiFi en arcs
  - Couleurs par etat : bleu (ecoute), violet (traitement), vert (parle), rouge (erreur)
- **Effets anneau LED** — 12 LEDs adressables avec animations distinctes :
  - *Veille* — lueur bleue tamisee
  - *Ecoute* — point bleu tournant
  - *Traitement* — onde violette sinusoidale
  - *Parle* — onde verte sinusoidale
  - *Erreur* — clignotement rouge
- **Son de demarrage** — deux notes ascendantes generees proceduralement (Do5 vers Sol5)
- **Controle du volume** — slider 0-100% expose dans Home Assistant, persistant entre les redemarrages
- **Traitement audio** — suppression de bruit niveau 4, gain automatique 31 dBFS

### Framework ESPHome

- ESP-IDF (version recommandee)
- PSRAM : mode octal, 80 MHz
- Version ESPHome minimale : 2024.11.0
- Packages partages : [`common/core.yaml`](common/core.yaml) (API, OTA, portail captif), [`common/wifi.yaml`](common/wifi.yaml) (WiFi WPA2 + AP de secours)

### Etats de l'assistant vocal

| Etat | ID | Ecran | Anneau LED | Description |
|---|---|---|---|---|
| Veille | 0 | Horloge + date | Bleu tamisee | En attente du mot de reveil |
| Ecoute | 1 | "Ecoute..." (bleu) | Point bleu tournant | Enregistrement de la parole |
| Traitement | 2 | "Traitement..." (violet) | Onde violette | STT + traitement en cours |
| Parle | 3 | "Parle..." (vert) | Onde verte | Lecture de la reponse TTS |
| Erreur | 4 | "Erreur" (rouge) | Clignotement rouge | Erreur pipeline (3s puis reset) |

## Boitier

Le boitier est un design parametrique OpenSCAD ([`enclosure/satellite.scad`](../enclosure/satellite.scad)) compose de deux pieces imprimees.

### Conception

- **Format** — puck cylindrique de 90 mm de diametre, incline a 15 degres pour orienter l'ecran et le micro vers l'utilisateur
- **Epaisseur de paroi** — 2 mm
- **Deux pieces :**
  - **Corps** — coque cylindrique avec grille haut-parleur en nid d'abeille sur le dessous, embases pour inserts M3 a chaud, collet press-fit pour le haut-parleur, et passage cable USB-C a l'arriere
  - **Face** — capot superieur affleurant avec fenetre ecran (34 mm), logement pour l'anneau LED (cavite 50 mm), port micro, et trous fraises M3

### Montage

1. Encastrer le haut-parleur en press-fit dans le collet au fond du corps (ouverture 40 mm)
2. Installer 3x inserts M3 a chaud dans les embases sur la surface inclinee du corps
3. Cabler et fixer l'ESP32-S3 a l'interieur du corps
4. Passer le cable USB-C par la fente arriere (14x8 mm)
5. Monter l'anneau LED et l'ecran dans le logement de la face
6. Fixer la face avec 3x vis M3 fraisees

### Impression

- STL pre-exportes dans [`enclosure/`](../enclosure/) : `body.stl`, `face.stl`, `spk_ring.stl`
- Pour personnaliser, ouvrir `satellite.scad` dans OpenSCAD et changer la variable `part` en `body`, `face` ou `assembly` (previsualisation)
- Recommande : PLA ou PETG, hauteur de couche 0.2 mm, remplissage 20%
- Imprimer la face en blanc ou translucide pour diffuser la lumiere de l'anneau LED

### Dimensions cles

| Parametre | Valeur |
|---|---|
| Diametre exterieur | 90 mm |
| Angle d'inclinaison | 15 degres |
| Epaisseur de paroi | 2 mm |
| Diametre haut-parleur | 40 mm |
| Fenetre ecran | 34 mm |
| Anneau LED exterieur | 50 mm |
| Fente cable | 14 x 8 mm |
| Fixation | 3x M3 sur PCD 78 mm |

## Flash du firmware

```bash
# Premier flash (USB)
esphome run satellite.yaml

# Mises a jour suivantes (OTA)
esphome run satellite.yaml --device esp-satellite.local
```

## Dependances

- [Home Assistant](https://www.home-assistant.io/) avec un pipeline vocal configure (Whisper STT + Piper TTS recommandes pour un fonctionnement entierement local)
- [ESPHome](https://esphome.io/) 2024.11.0+
- [OpenSCAD](https://openscad.org/) (uniquement pour personnaliser le boitier)

## Licence

Projet personnel partage tel quel. Libre d'utilisation et de modification.
