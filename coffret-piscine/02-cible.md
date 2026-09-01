# 02 — Cible

## Principe

Trois idées, dans cet ordre d'importance :

1. **L'asservissement matériel reste maître.** Les relais R3/R4 s'insèrent *en série*
   derrière le pôle 2 du contacteur — ils n'apportent pas leur propre phase. Pompe à
   l'arrêt → électrolyseur et pompe pH physiquement hors tension, quoi qu'en pensent HA,
   l'ESP ou une automatisation ratée. Doser de l'acide ou électrolyser dans une eau
   immobile, c'est une cellule abîmée, une sonde pH faussée et de l'hydrogène qui
   s'accumule. Ça ne se confie pas à du logiciel.
2. **Le logiciel vient par-dessus, jamais à la place.**
3. **Le coffret reste pilotable sans HA.** Horloge mécanique conservée en parallèle du
   relais pompe, bouton d'éclairage conservé en face avant.

## Schéma cible

```
ARRIVÉE 230 V ── Q0 inter général (porte)
  │  L
  ├─[Q1  C2  2A]──── Carte ESP32 4 relais «piscinev4» (alim L/N)
  │                  → sous tension en permanence, HA garde la main même pompe à l'arrêt
  │
  ├─[Q2  C4  4A]──── R2 COM ─┤├─ NO ── [CTN 5 Ω] ── TR1 primaire ── 12 V ── projecteur
  │                  S1 bouton bleu : plus aucune puissance
  │                       → bloc 1 recâblé en contact sec vers GPIO (TBTS)
  │                       → bloc 2 DÉPOSÉ (fil vers A1 supprimé)
  │
  │   phase commande ── S2 AUTO/MANU
  │      [Q1 ou Q2]       ├─ MANUEL ────────────────────────┐
  │      point ouvert n°1 └─ AUTO ── KH1 horloge 1 ──→ 4 ───┤
  │                                      ‖                  │
  │                                R1 COM ┤├ NO             ▼
  │                           (en parallèle de l'horloge)  KM1 bobine A1
  │                                                          │  A2 → N
  │
  ├─[Q3  C6  6A]──── KM1 pôle 2  3L2 ──→ 4T2 ─┬─ R3 COM ┤├ NO ── électrolyseur
  │                                           └─ R4 COM ┤├ NO ── régulateur pH
  │
  └─[Q4  Z-MS 6,3A]── KM1 pôle 1  1L1 ──→ 2T1 ── M pompe
                      KM1 pôle 3  5L3 ──→ 6T3 ── (réserve)

   N ── bornier neutre ── retours neutres de TR1, électrolyseur, régul pH, A2
```

Les relais ne coupent **que la phase**. Tous les neutres partent directement au bornier N.

## Affectation des relais

Carte ESP32 4 relais, `esphome/piscinev4.yaml` :

| Relais | GPIO | Circuit | Source de phase | Entité HA |
|---|---|---|---|---|
| **R1** | 32 | Bobine contacteur KM1 | Circuit de commande, en travers des bornes horloge 1/4 | `switch.piscine_relais` |
| **R2** | 33 | Éclairage (primaire TR1) | Q2 | `switch.piscine_eclairage` |
| **R3** | 25 | Électrolyseur | KM1 4T2 (asservi) | `switch.piscine_electrolyse` |
| **R4** | 26 | Régulation pH | KM1 4T2 (asservi) | `switch.piscine_regulation_ph` |

R1 reprend le rôle de la carte ESP8266 actuelle, qui part à la retraite. Un seul appareil,
un seul jeu d'interverrouillages, un seul point de défaillance à raisonner.

⚠️ **`switch.piscine_relais` est référencé par 8 automatisations, les dashboards et le
système de scheduled-actions.** L'entity_id doit être préservé à l'identique — procédure
en [04-esphome-ha.md](04-esphome-ha.md).

## Points de conception

### R1 pilote la bobine, jamais le moteur

Le Z-MS et le DILM7 restent strictement en place. Le relais commute ~5 VA de bobine, pas
1,1 kW de moteur.

### Horloge conservée en parallèle de R1

Programmée sur une plage minimale en heures creuses (4 h). Si l'ESP perd le WiFi, ou si
`RESTORE_DEFAULT_OFF` s'applique après une coupure secteur, la piscine filtre quand même.
Ça ne coûte rien et ça évite une eau verte au retour de vacances.

Logique OU : R1 fermé → phase sur A1 ; contact horloge fermé → phase sur A1. Quand R1
ferme, la phase remonte aussi sur la borne 4 de l'horloge, dont le contact est ouvert —
sans effet. Pas de retour parasite.

### Éclairage : commuter le PRIMAIRE, jamais le secondaire

300 W sous 12 V = **25 A**. Un contact de relais 10 A n'y survit pas. On commute le
230 V en amont du transfo.

### CTN d'appel obligatoire sur le transfo toroïdal

Un toroïdal a un appel magnétisant de **20 à 60× son nominal**. Ce Q2 en 4 A courbe C pour
une charge d'~1,3 A, c'est l'installateur qui signale que l'appel est bien réel. Un contact
de relais 10 A va se piquer puis finir par se **souder fermé** — et un projecteur qu'on ne
peut plus éteindre, c'est le genre de panne qu'on découvre tard.

**CTN de limitation d'appel en série sur le primaire** : SCK-054 (5 Ω / 5 A) ou équivalent.
2 €, monté sur le fil de phase entre R2-NO et le primaire. Alternative si le projecteur est
resté en halogène 300 W : faire piloter un petit contacteur par R2.

### Le bouton bleu passe en entrée sèche

Deux options, à trancher selon le point ouvert n°4 de [01-existant.md](01-existant.md) :

| | Bouton = puissance (simple) | Bouton = entrée GPIO (retenu) |
|---|---|---|
| Câblage | R2 en parallèle du bouton | Bouton → GPIO en TBTS, R2 seul en puissance |
| Comportement | Logique OU : HA ne peut pas éteindre ce que le bouton a accroché | Bouton = toggle dans ESPHome, HA a la main pleine |
| Prérequis | aucun | un GPIO libre sorti sur la carte |

Le bloc de contact de S1 est prévu pour 250 V, y faire passer 3,3 V ne pose aucun problème.
Il faut en revanche **écarter physiquement cette paire des cheminements 230 V** dans le
coffret (TBTS ≠ BT, on ne les fait pas voyager ensemble dans la même goulotte).

### Le couplage éclairage → pompe repasse en logiciel

Le fil du bloc 2 de S1 vers A1 est déposé. Le comportement voulu par l'installateur est
recréé côté HA — projecteur allumé → pompe démarrée — avec un `input_boolean` de
contournement pour les cas où on veut la lumière sans filtrer. Voir
[04-esphome-ha.md](04-esphome-ha.md).

### L'état HA des auxiliaires ne veut plus dire « alimenté »

R3 fermé + pompe à l'arrêt = électrolyseur hors tension. Il faut donc distinguer
**armé** (état du relais) et **actif** (relais ET pompe), sinon le dashboard ment la
moitié de la journée. Deux `binary_sensor` template côté ESPHome s'en chargent.

## Nomenclature

| Qté | Article | Note |
|---|---|---|
| 1 | CTN de limitation d'appel SCK-054 (5 Ω / 5 A) | Primaire TR1 |
| 1 | Support rail DIN ou boîtier DIN pour la carte ESP32 | Ne pas laisser la carte nue sur un flanc |
| — | Fil H07V-K 1,5 mm² rouge / bleu / vert-jaune | Puissance |
| — | Fil 0,75 mm² ou paire torsadée | Liaison bouton → GPIO (TBTS) |
| — | Embouts de câblage 1,5 et 0,75 | **Un embout par conducteur, sans exception** |
| — | Bagues de repérage numérotées | Repérer avant de déposer quoi que ce soit |
| 1 | Bornier de répartition N (si le bornier existant est saturé) | 4 départs neutres à ajouter |

Outillage : VAT, multimètre avec fonction continuité, tournevis isolés 1000 V.

## Ce qui ne change pas

- Z-MS-6,3/3, réglage 6,3 A — ne pas y toucher
- DILM7 et son câblage de puissance pôles 1 et 2
- Commutateur AUTO/MANU (avec sa conséquence : en MANUEL, HA n'a pas la main sur la pompe)
- Voyant-bouton vert MARCHE/ARRÊT
- Horloge MicroRex, à reprogrammer en secours
