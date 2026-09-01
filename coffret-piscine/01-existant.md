# 01 — Existant

## Inventaire

Coffret IDE (EN 61439-1/-3), interrupteur général rotatif sur la porte, IP65.

| Repère | Marquage | Rôle |
|---|---|---|
| Q0 | Rotatif de porte | Sectionnement général du coffret |
| Q1 | Eaton **PLS4-C2/1N** — 2 A, 1P+N | Alimentation 230 V de la carte WiFi (ajout postérieur) |
| Q2 | Eaton **PLS4-C4/1N** — 4 A, 1P+N | **Éclairage** : transfo toroïdal → projecteur 12 V |
| Q3 | Eaton **PLS4-C6/1N** — 6 A, 1P+N | **Commande + auxiliaires asservis** : bobine, électrolyseur, régul pH |
| Q4 | Eaton **Z-MS-6,3/3** | Disjoncteur moteur pompe (3 pôles, plage 4–6,3 A) |
| KM1 | Eaton **DILM7**, bobine 230 V 50 Hz | Contacteur **tripolaire** — commute plusieurs circuits |
| KH1 | Rex **MicroRex T31** — 16 A, cos φ=1 | Horloge mécanique journalière, contact 1 → 4 |
| TR1 | Transfo toroïdal ~100–300 VA | 230 V → 12 V projecteur |
| S1 | Bouton bleu à accrochage, face avant | Éclairage — **2 blocs de contact** |
| S2 | Commutateur AUTOMATIQUE / MANUEL | Sélection horloge / marche forcée |
| S3 | Voyant-bouton vert MARCHE / ARRÊT | Signalisation + commande manuelle pompe |
| A1 | Carte relais WiFi ESP8266 (`esphome/piscine.yaml`) | 1 relais GPIO5 → `switch.piscine_relais` |

### Le Z-MS n'est pas un disjoncteur ordinaire

C'est un **disjoncteur moteur** : magnétique (court-circuit) + **thermique réglé à 6,3 A**
(surcharge) + sectionnement manuel. C'est pour ça que la pompe n'a pas de C-quelque-chose :
un moteur qui cale tire 3–4× son nominal sans jamais atteindre le seuil magnétique d'un
C10 — il chauffe tranquillement jusqu'à la casse. Seul le thermique du Z-MS déclenche.

### Le DILM7 est tripolaire sur une installation monophasée

C'est le point structurant de tout le coffret. Personne ne met un contacteur 3 pôles pour
commuter une seule phase : il est là parce qu'il commute **plusieurs circuits d'un coup**.

- **Pôle 1** (1L1 → 2T1) : phase pompe, depuis Q4
- **Pôle 2** (3L2 → 4T2) : phase auxiliaires → électrolyseur + régulation pH
- **Pôle 3** (5L3 → 6T3) : à vérifier, probablement libre

Conséquence : **l'électrolyseur et le régulateur pH sont déjà asservis matériellement à
la pompe.** Ils n'ont aucune commande propre — pompe ON = les deux ON, sans nuance.
C'est exactement le manque que ce projet comble.

## Relevés terrain — 2026-07-24

Coffret sous tension, coupure sélective d'un départ à la fois :

| Action | Observation | Conclusion |
|---|---|---|
| Coupure Q3 (C6) seul | Régulation pH **et** électrolyse coupées | Q3 alimente la branche auxiliaires |
| Coupure Q2 (C4) seul | Éclairage coupé | Q2 = éclairage (transfo) |
| **Pompe en marche**, coupure Q3 (C6) | **La pompe continue de tourner** | **Variante A confirmée** : Q3 alimente le pôle 2 (3L2) en direct, et **pas** la bobine |
| — | Le relais WiFi ne commande la pompe que via les bornes horloge 1 / 4 | Le relais est en travers du contact d'horloge |
| — | Q1 (C2) alimente la carte WiFi | Source du circuit de commande encore indéterminée |

Le relais WiFi n'agit donc que si S2 est sur **AUTOMATIQUE**. En MANUEL la pompe est
forcée quoi que dise Home Assistant.

## Schéma source

```
ARRIVÉE 230 V ── Q0 inter général (porte)
  │  L
  ├─[Q1  C2  2A]──── Carte WiFi ESP8266  (alim L/N)
  │                    └─ relais GPIO5, contact sec ──┐ en travers de KH1
  │                  ( + circuit de commande ?  ← point ouvert n°1 )
  │
  ├─[Q2  C4  4A]──── S1 bouton bleu «éclairage»       │
  │                    ├─ bloc 1 ── TR1 primaire ── 12 V ── projecteur
  │                    └─ bloc 2 ──────────────────────────────┐
  │                       (c'est CE fil qui démarre la pompe)  │
  │                  ( + circuit de commande ?  ← point ouvert n°1 )
  │                                                            │
  │   phase commande ─── S2 AUTO/MANU                          │
  │        [Q1 ou Q2]      ├─ MANUEL ──────────────────────────┤
  │                        └─ AUTO ── KH1 horloge 1 ──→ 4 ─────┤
  │                                        ‖                   ▼
  │                                  (relais WiFi)      KM1 bobine A1
  │                                                            │ A2 → N
  ├─[Q3  C6  6A]──── KM1 pôle 2   3L2 ──→ 4T2 ─┬─ électrolyseur
  │                                            └─ régulateur pH
  │
  └─[Q4  Z-MS 6,3A]── KM1 pôle 1  1L1 ──→ 2T1 ── M pompe
                      KM1 pôle 3  5L3 ──→ 6T3 ── (libre ?)

   N ── bornier neutre ── retours TR1, électrolyseur, régul pH, KM1 A2
```

Lecture : Q3 ne fait **que** de la puissance auxiliaire, via le pôle 2. Il ne participe pas
à la commande — d'où la pompe qui continue de tourner quand on le coupe.

Il reste **deux arrivées de phase distinctes sur A1** : le circuit de commande (par S2 puis
l'horloge) et le bloc 2 du bouton d'éclairage. Selon la réponse au point ouvert n°1, elles
viennent soit de la même protection (Q2), soit de deux protections différentes (Q1 et Q2).
Dans les deux cas la conclusion pratique est la même : **couper Q0**, jamais un départ isolé.

Le couplage éclairage → pompe est donc **un seul fil**, du bloc 2 de S1 vers A1. C'est
la justification de l'installateur : projecteur allumé sans circulation = on voit les
dépôts et les particules en suspension.

**Confirmé par l'installateur** (de mémoire, à la pose) : le couplage se défait en
retirant *un seul fil*, sans qu'il ait voulu dire lequel.

✅ **Identifié et déposé le 2026-07-24** — conducteur **brun**, cheminant du bouton bleu
S1 vers A1 en transitant par le bornier du sélecteur AUTO/MARCHE/ARRÊT. Déposé **côté
bouton** et extrémité cossée ; l'autre extrémité reste raccordée sur A1. Le projecteur
s'allume désormais sans démarrer la pompe.

Le conducteur est donc encore **sous tension quand la bobine est excitée** (pompe en
marche), mais isolé. Acceptable en l'état ; il est retiré intégralement à l'étape 4 du
[runbook](03-runbook.md#étape-4--éclairage-r2), quand le bloc 1 de S1 passe en entrée
sèche et que le bloc 2 est déposé.

## Points ouverts

### 1. Quelle protection alimente le circuit de commande (S2 → horloge → bobine) ?

Réglé pour Q3 : le test « pompe en marche, coupure Q3 » l'a laissée tourner, donc **Q3
n'alimente pas la bobine**. Il ne reste que Q1 (C2) ou Q2 (C4).

- **Hypothèse 1 — commande sur Q1 (C2).** C'est le schéma d'origine classique : un 2 A
  dédié au circuit de commande (moteur d'horloge + bobine ≈ quelques VA), sur lequel la
  carte WiFi a simplement été greffée après coup. Le calibre 2 A colle parfaitement ;
  personne ne pose un 2 A juste pour une alim à découpage de 3 W.
- **Hypothèse 2 — commande sur Q2 (C4).** Alors éclairage et commande partagent la même
  protection, ce qui explique élégamment que le bloc 2 du bouton puisse attaquer A1 sans
  mélanger deux départs.

**Test décisif** — mettre S2 sur **MANUEL** (marche forcée, qui court-circuite l'horloge
et le relais WiFi), pompe en marche, puis :

1. couper **Q1** → la pompe s'arrête ? **commande sur C2** (hypothèse 1)
2. sinon couper **Q2** → la pompe s'arrête ? **commande sur C4** (hypothèse 2)

⚠️ Le passage par MANUEL est indispensable. En AUTO, couper Q1 coupe l'alimentation de la
carte WiFi, dont le relais retombe et arrête la pompe — l'arrêt ne prouverait rien.

Incidence sur le projet : **nulle sur le câblage cible** (R1 reste en travers des bornes
horloge 1/4, quelle que soit l'origine de la phase). L'enjeu est la justesse du schéma et
la consignation : savoir quoi couper pour intervenir.

### 2. Le pôle 3 (5L3/6T3) est-il libre ?

Bornes vides à vérifier visuellement. Pas nécessaire au projet, mais c'est un chemin de
commutation asservi disponible pour plus tard (surpresseur robot, chauffage…).

### 3. Carte ESP32 4 relais — les COM sont-ils indépendants ?

Continuité **COM1 ↔ COM2** carte hors tension. La LC-Tech X4 a normalement un jeu
COM/NO/NC séparé par voie ; si les COM sont pontés en interne, le schéma cible tombe
(il faudrait une source de phase unique pour les quatre relais). Bloquant.

### 4. Un GPIO libre est-il sorti sur la carte ?

Détermine si le bouton bleu peut devenir une entrée sèche (voir [02-cible.md](02-cible.md)).

### 5. Différentiel 30 mA en amont ?

Aucun dans ce coffret. À confirmer dans le tableau maison. Prioritaire sur le reste.
