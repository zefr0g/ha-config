# Coffret piscine — passage en 4 relais pilotés par Home Assistant

Refonte de la commande du coffret piscine IDE : passer d'un relais WiFi unique
(pompe seule, en lieu et place de l'horloge) à une carte ESP32 4 relais qui pilote
**pompe / éclairage / électrolyseur / régulation pH** indépendamment — sans perdre
l'asservissement matériel qui interdit électrolyse et dosage sans circulation.

| Doc | Contenu |
|---|---|
| [01-existant.md](01-existant.md) | Inventaire du coffret, schéma **source**, relevés terrain et points encore ouverts |
| [02-cible.md](02-cible.md) | Schéma **cible**, affectation des 4 relais, nomenclature matériel |
| [03-runbook.md](03-runbook.md) | Procédure de câblage pas à pas + tests de recette |
| [04-esphome-ha.md](04-esphome-ha.md) | Config ESPHome, migration de `switch.piscine_relais`, automatisations HA |

**Résumé en une ligne :** l'asservissement pH/électrolyse **existe déjà** (pôle 2 du
contacteur tripolaire) — le chantier consiste à *insérer* deux relais en série derrière
ce pôle, à sortir l'éclairage du bouton 230 V, et à supprimer le pont qui fait démarrer
la pompe quand on allume le projecteur.

## État

- Relevés faits sur site le 2026-07-24 (coffret sous tension, coupure sélective des départs).
  Topologie des auxiliaires **confirmée** : ils pendent au pôle 2 du contacteur, alimenté
  par C6 — c'est l'asservissement à réutiliser.
- **Étape 1 faite le 2026-07-24** : le fil brun du couplage éclairage → pompe est déposé
  côté bouton et cossé. Le projecteur s'allume sans démarrer la pompe. Le conducteur est
  retiré intégralement à l'étape 4.
- Reste du câblage **non commencé**. Points encore à confirmer avant de toucher au cuivre :
  voir « Points ouverts » dans [01-existant.md](01-existant.md#points-ouverts). Le seul
  bloquant est la séparation des COM sur la carte 4 relais.

## Sécurité

Coffret 230 V en local technique piscine. Coupure à l'inter général de la porte + VAT
avant toute intervention — couper un seul disjoncteur ne suffit pas, les départs sont
alimentés par des protections différentes (voir schéma source).

**Point de conformité à vérifier en priorité :** aucun dispositif différentiel 30 mA
n'est présent dans ce coffret (les PLS4 sont de simples disjoncteurs). Les circuits
piscine doivent être protégés en 30 mA — à confirmer en amont, dans le tableau maison.
