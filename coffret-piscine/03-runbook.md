# 03 — Runbook

Ordre imposé : on lève les inconnues **avant** d'acheter, on valide la carte **sur établi**
avant de la poser, on câble **un circuit à la fois** en testant entre chaque.

Règle permanente : coupure à **Q0 (inter général de porte)** + VAT avant toute intervention.
Couper un seul disjoncteur ne suffit pas — deux protections différentes ramènent de la phase
sur la bobine.

---

## Phase 0 — Lever les inconnues (~30 min, sans rien démonter)

| # | Test | Réponse attendue | Si autre |
|---|---|---|---|
| 0.1 | ~~Pompe en marche, couper Q3~~ | ✅ **Fait 2026-07-24** — pompe toujours en marche → variante A, Q3 alimente 3L2 en direct | — |
| 0.2 | **S2 sur MANUEL**, pompe forcée : couper Q1, puis Q2 | Celui qui arrête la pompe alimente le circuit de commande | Aucun des deux → tracer l'amont de S2 |
| 0.3 | Hors tension : bornes **5L3 / 6T3** de KM1 | Vides → pôle 3 en réserve | Occupé → tracer, ne pas y toucher |
| 0.4 | Carte ESP32 hors tension : continuité **COM1 ↔ COM2** | Isolé | **Bloquant** — COM pontés, voir plus bas |
| 0.5 | Carte ESP32 : un GPIO libre est-il sorti sur connecteur ? | Oui → bouton en entrée sèche | Non → option « bouton = puissance » |
| 0.6 | Tableau maison : différentiel 30 mA en amont du coffret ? | Oui | **Traiter en priorité, avant ce chantier** |

**0.2 — le passage par MANUEL est indispensable.** En AUTO, couper Q1 coupe l'alimentation
de la carte WiFi, dont le relais retombe et arrête la pompe : l'arrêt ne prouverait rien.
MANUEL court-circuite horloge et relais, on ne teste plus que l'origine de la phase.

Ce test ne conditionne aucun choix de câblage — R1 reste en travers des bornes horloge 1/4
quelle que soit la réponse. Il sert à la justesse du schéma et à la consignation.

**Si 0.4 échoue** (COM pontés en interne) : les quatre relais ne peuvent pas avoir des
sources de phase différentes. Deux issues — soit couper la piste de pontage sur la carte
(à confirmer faisable), soit changer de carte pour un modèle à COM séparés. Ne pas
contourner en alimentant tout depuis une seule source : ça détruirait l'asservissement.

---

## Étape 1 — Identifier et déposer le fil du couplage éclairage → pompe

> ✅ **Fait le 2026-07-24.** Le fil est un **brun**, du bouton bleu S1 vers A1, transitant
> par le bornier du sélecteur AUTO/MARCHE/ARRÊT. Déposé **côté bouton**, extrémité cossée ;
> l'autre extrémité reste sur A1. Le projecteur s'allume sans démarrer la pompe.
>
> Le conducteur reste sous tension quand la bobine est excitée, mais isolé — état
> acceptable. Il est retiré intégralement à l'[étape 4](#étape-4--éclairage-r2).

C'est le fil que l'installateur n'a pas voulu nommer. Il part du **bloc de contact n°2 du
bouton bleu S1** et arrive sur **A1 de KM1**.

### Identification

Sur A1 arrivent plusieurs conducteurs : depuis la borne 4 de l'horloge, depuis la position
MANUEL de S2, et celui qu'on cherche. Deux façons de le distinguer :

**Par le faisceau** — les commandes de face avant sont sur la porte. Le fil recherché fait
partie du toron souple porte ↔ châssis. C'est le seul arrivant sur A1 qui vient de la porte
*et* remonte au bouton bleu (les autres viennent de S2 et de l'horloge, sur rail).

**Par la mesure** (méthode sûre, hors tension) — bouton bleu **enclenché** (contact fermé) :
continuité entre l'entrée du bloc 2 de S1 et A1. Bouton relâché : la continuité disparaît.
C'est la preuve formelle.

### Vérification avant dépose

Coffret sous tension, S2 sur AUTO, relais HA ouvert, pompe à l'arrêt. Appuyer sur le bouton
bleu → le projecteur s'allume **et** la pompe démarre. Mesurer 230 V entre A1 et N.
On tient bien le bon point.

### Dépose

⚠️ **Déposer le conducteur aux DEUX extrémités**, ou retirer carrément le bloc de contact n°2
du bouton. Débranché du seul côté A1, il reste sous tension côté bouton dès que Q2 est fermé
et que le bouton est enclenché — un fil vivant qui pendouille dans un coffret, c'est non.

Dans le schéma cible le bloc 2 disparaît de toute façon : le bloc 1 est réaffecté en contact
sec vers le GPIO, et la puissance de l'éclairage passe par R2.

### Recette

Sous tension : appuyer sur le bouton bleu → le projecteur s'allume, **la pompe ne démarre
pas**. Le relais HA commande toujours la pompe normalement.

À ce stade le découplage est fait et le coffret est fonctionnel — on peut s'arrêter là et
faire le reste plus tard.

---

## Étape 2 — Préparer la carte sur établi

Hors du coffret, carte alimentée en 230 V sur un cordon dédié, **rien de câblé sur les
contacts**.

1. Flasher `esphome/piscinev4.yaml` (voir [04-esphome-ha.md](04-esphome-ha.md)).
2. Vérifier que les 4 relais claquent depuis HA, dans le vide, et que le mapping
   GPIO → repère R1..R4 correspond bien à la sérigraphie de la carte.
3. Couper l'alimentation, la rétablir : vérifier les `restore_mode` (R1 et R2 à OFF,
   R3 et R4 à ON).
4. Si option entrée sèche : ponter le GPIO à la masse à la pince → R2 doit basculer.
5. Contrôler la portée WiFi **à l'emplacement définitif, porte du coffret fermée** —
   coffret métallique ? plastique IP65, donc a priori transparent, mais à mesurer
   (`sensor.piscinev4_wifi_signal`, viser mieux que −75 dBm).

Ne pas poser la carte dans le coffret tant que ces 5 points ne passent pas.

---

## Étape 3 — Migration de la commande pompe (R1)

1. Q0 ouvert, VAT.
2. Repérer et photographier le câblage du relais ESP8266 actuel sur les bornes horloge 1/4.
3. Déposer la carte ESP8266. **Laisser l'horloge câblée** — elle devient le secours.
4. Poser la carte ESP32 sur son support DIN, alimentation L/N depuis Q1.
5. Reprendre le contact sec sur les bornes horloge 1/4, cette fois depuis **R1 COM / R1 NO**.
6. Côté HA : supprimer l'ancien appareil ESPHome `piscine` **avant** d'adopter le nouveau
   (sinon `switch.piscine_relais_2`) — procédure détaillée en
   [04-esphome-ha.md](04-esphome-ha.md#migration-de-lentity_id).

### Recette

- S2 sur AUTO, `switch.piscine_relais` ON → le contacteur colle, la pompe tourne, pH et
  électrolyseur s'alimentent.
- OFF → tout retombe.
- Forcer l'horloge sur une plage active, relais HA à OFF → la pompe tourne (secours OK).
- Les 8 automatisations piscine et le dashboard répondent toujours.

---

## Étape 4 — Éclairage (R2)

1. Q0 ouvert, VAT.
2. Insérer la **CTN** en série sur le fil de phase entre R2-NO et le primaire de TR1.
3. Phase depuis Q2 → R2 COM. R2 NO → CTN → primaire TR1. Neutre du transfo → bornier N.
4. Bloc 1 de S1 recâblé en contact sec vers le GPIO retenu, en **paire séparée** des
   cheminements 230 V.

### Recette

- `switch.piscine_eclairage` ON/OFF → le projecteur suit.
- Bouton bleu → bascule l'éclairage, et l'état remonte dans HA.
- 10 cycles ON/OFF d'affilée : pas de déclenchement de Q2, pas de collage du relais
  (couper puis vérifier que le projecteur s'éteint bien à chaque fois).

---

## Étape 5 — Auxiliaires (R3 / R4)

Départs confirmés sur le pôle 2 (variante A, test 0.1 du 2026-07-24).

1. Q0 ouvert, VAT.
2. Repérer les départs actuels électrolyseur et régulation pH sur **4T2**.
3. Les déposer de 4T2 et les reprendre sur **R3 NO** et **R4 NO**.
4. Ponter **4T2 → R3 COM** et **4T2 → R4 COM**.
5. Neutres inchangés, au bornier N.

### Recette — c'est le test de sécurité, ne pas le sauter

| Pompe | R3/R4 | Attendu |
|---|---|---|
| OFF | ON | Électrolyseur et régul pH **hors tension** (mesurer 0 V à leurs bornes) |
| ON | OFF | Pompe tourne, auxiliaires hors tension |
| ON | ON | Tout fonctionne |
| ON → OFF pendant fonctionnement | ON | Les auxiliaires tombent **immédiatement** avec le contacteur |

La première ligne est la raison d'être de tout le montage. Mesurer, ne pas déduire.

---

## Étape 6 — Reprise logicielle

1. Reprogrammer l'horloge MicroRex sur une plage minimale en heures creuses (~4 h).
2. Créer `input_boolean.piscine_eclairage_sans_filtration` dans `input_boolean_piscine.yaml`.
3. Ajouter l'automatisation éclairage → pompe (voir [04-esphome-ha.md](04-esphome-ha.md)).
4. Ajouter les tuiles éclairage / électrolyse / pH au `dashboard_piscine.yaml`, en
   affichant l'état **actif** (relais ET pompe) et non l'état **armé**.
5. Repérer physiquement le coffret : étiqueter Q1..Q4 et les 4 relais.
6. Mettre à jour [01-existant.md](01-existant.md) avec les réponses de la phase 0 —
   variante A ou B, pôle 3, COM, GPIO, différentiel.

---

## Points de vigilance transverses

- **Un embout par conducteur.** Sans exception, y compris sur les contacts de la carte.
- **TBTS et 230 V ne voyagent pas ensemble.** La paire du bouton passe à part.
- **Ne jamais commuter le secondaire 12 V** du transfo (25 A).
- **Ne pas toucher au réglage 6,3 A du Z-MS.**
- En **MANUEL**, S2 court-circuite toute la commande : HA n'a pas la main sur la pompe.
  Comportement voulu (marche forcée de dépannage), mais à garder en tête au moment de
  diagnostiquer un « HA dit OFF mais ça tourne ».
- La carte reste alimentée par Q1 en permanence : couper la pompe ne coupe pas l'ESP,
  HA garde la visibilité. C'est voulu.
