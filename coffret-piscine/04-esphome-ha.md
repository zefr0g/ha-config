# 04 — ESPHome & Home Assistant

## Config ESPHome cible

Remplace `esphome/piscinev4.yaml` (l'actuel est une config générée, hors convention du
dépôt : `api: null`, pas de packages, clés alphabétisées). Version proposée, alignée sur
`esphome/piscine.yaml` :

```yaml
substitutions:
  name: piscinev4

packages:
  core: !include common/core.yaml
  wifi: !include common/wifi.yaml

esphome:
  name: ${name}

esp32:
  board: esp32dev
  framework:
    type: esp-idf

status_led:
  pin: GPIO23

switch:
  # R1 — bobine du contacteur KM1. Reprend l'entity_id de l'ancienne carte ESP8266.
  - platform: gpio
    id: relay_pompe
    name: "Piscine Relais"
    pin: GPIO32
    restore_mode: RESTORE_DEFAULT_OFF

  # R2 — primaire du transfo éclairage (via CTN d'appel)
  - platform: gpio
    id: relay_eclairage
    name: "Piscine Éclairage"
    pin: GPIO33
    restore_mode: RESTORE_DEFAULT_OFF

  # R3/R4 — auxiliaires. Asservis matériellement au pôle 2 de KM1 : ces relais ne font
  # qu'armer. Restaurés à ON pour qu'ils reprennent le service avec la pompe après coupure.
  - platform: gpio
    id: relay_electrolyse
    name: "Piscine Électrolyse"
    pin: GPIO25
    restore_mode: RESTORE_DEFAULT_ON

  - platform: gpio
    id: relay_ph
    name: "Piscine Régulation pH"
    pin: GPIO26
    restore_mode: RESTORE_DEFAULT_ON

binary_sensor:
  # « Armé » (état du relais) n'est pas « alimenté ». Ces deux capteurs donnent le réel.
  - platform: template
    name: "Piscine Électrolyse active"
    lambda: 'return id(relay_pompe).state && id(relay_electrolyse).state;'

  - platform: template
    name: "Piscine Régulation pH active"
    lambda: 'return id(relay_pompe).state && id(relay_ph).state;'

  # Bouton bleu de face avant, recâblé en contact sec (TBTS).
  # ⚠️ GPIO à adapter au connecteur réellement sorti sur la carte (point ouvert n°4).
  #    Sur GPIO34/35/36/39 (entrées seules) le pull-up interne n'existe pas :
  #    prévoir une résistance 10 kΩ vers 3V3.
  - platform: gpio
    id: bouton_eclairage
    name: "Piscine Bouton Éclairage"
    pin:
      number: GPIO27
      mode:
        input: true
        pullup: true
      inverted: true
    filters:
      - delayed_on: 30ms
    on_press:
      - switch.toggle: relay_eclairage
```

### Notes

- Pas d'interverrouillage logiciel sur R3/R4 : la sécurité est **matérielle** (pôle 2 du
  contacteur). Un interlock ESPHome par-dessus ne ferait qu'ajouter un mode de panne et
  masquer la vraie protection.
- `RESTORE_DEFAULT_ON` sur R3/R4 est délibéré : après coupure secteur, les auxiliaires
  doivent repartir avec la pompe sans intervention. Ils restent inoffensifs hors
  circulation, puisque hors tension.
- `common/core.yaml` fournit déjà api chiffrée, OTA, logger, uptime, wifi_signal, version —
  ne pas les redéclarer.

## Migration de l'entity_id

`switch.piscine_relais` est référencé par les 8 `automations/automation_piscine_*.yaml`,
`dashboard_piscine.yaml` et le système de scheduled-actions. Si le nouvel appareil est
adopté alors que l'ancien est encore dans le registre, HA attribue
`switch.piscine_relais_2` et **tout casse en silence** — les automatisations ne lèvent pas
d'erreur, elles ne font simplement plus rien.

Ordre impératif :

1. Vérifier l'inventaire des références avant de commencer :
   ```bash
   grep -rn "piscine_relais" --include="*.yaml" --include="*.py" .
   ```
2. Déposer physiquement la carte ESP8266 (étape 3 du runbook).
3. Dans HA : **Paramètres → Appareils → ESPHome → `piscine` → Supprimer**.
   Vérifier dans Outils de développement → États que `switch.piscine_relais` a disparu.
4. Flasher et mettre en service la carte ESP32.
5. Adopter le nouvel appareil `piscinev4`.
6. Confirmer que l'entité créée est bien `switch.piscine_relais` (et non `_2`).
7. Archiver ou supprimer `esphome/piscine.yaml` du dépôt.

Si un `_2` apparaît malgré tout : supprimer l'entité fantôme dans le registre, puis
renommer l'entity_id à la main dans l'UI. Ne **pas** faire un chercher-remplacer dans le
dépôt pour s'adapter au `_2` — l'entity_id est le contrat, c'est lui qu'on préserve.

## Automatisation éclairage → pompe

Recrée en logiciel le comportement du fil déposé à l'étape 1, avec la porte de sortie que
le câblage d'origine n'offrait pas.

`automations/automation_piscine_7_eclairage_pompe.yaml` :

```yaml
alias: "Piscine 7 — Éclairage allumé, démarrer la pompe"
description: >
  Remplace le pont matériel bouton d'éclairage → bobine du contacteur, déposé lors du
  passage en 4 relais. Projecteur allumé sans circulation = dépôts et particules visibles.
  Contournable via input_boolean.piscine_eclairage_sans_filtration.
trigger:
  - platform: state
    entity_id: switch.piscine_eclairage
    to: "on"
condition:
  - condition: state
    entity_id: input_boolean.piscine_eclairage_sans_filtration
    state: "off"
  - condition: state
    entity_id: switch.piscine_relais
    state: "off"
action:
  - service: switch.turn_on
    target:
      entity_id: switch.piscine_relais
mode: single
```

Volontairement **asymétrique** : allumer le projecteur démarre la pompe, mais l'éteindre
ne l'arrête pas. La filtration a sa propre logique (surplus solaire, objectif journalier,
heures creuses) — l'éclairage n'a pas à décider de son arrêt.

Helper à ajouter dans `input_boolean_piscine.yaml` :

```yaml
piscine_eclairage_sans_filtration:
  name: "Éclairage sans filtration"
  icon: mdi:lightbulb-off-outline
```

## Dashboard

Dans `dashboard_piscine.yaml`, afficher pour les auxiliaires l'état **actif** et non
l'état **armé** :

| Tuile | Entité de commande | Entité d'état |
|---|---|---|
| Pompe | `switch.piscine_relais` | idem |
| Éclairage | `switch.piscine_eclairage` | idem |
| Électrolyse | `switch.piscine_electrolyse` | `binary_sensor.piscine_electrolyse_active` |
| Régulation pH | `switch.piscine_regulation_ph` | `binary_sensor.piscine_regulation_ph_active` |

Sans ça, les tuiles électrolyse et pH s'affichent allumées toute la nuit alors que les
appareils sont hors tension.

⚠️ Rappel dépôt : `confirmation.text` d'une `tap_action` Lovelace **ne rend pas le Jinja**
— chaînes statiques uniquement.

## Ce qui reste hors périmètre

- Interlock logiciel sur R3/R4 — inutile, la sécurité est câblée.
- Mesure de courant / confirmation que la pompe tourne réellement (pince ampèremétrique
  ou détection de débit). Intéressant, mais c'est un autre chantier.
- Utilisation du pôle 3 de KM1, s'il est libre.
