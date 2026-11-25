# Contrôle des factures au regard des contrats de copropriété

Cet outil compare **chaque ligne de facture** au **contrat de la copropriété concernée** et produit un
**rapport Excel trié par immeuble**. Pour chaque ligne, il vérifie :

| Contrôle | Statut affiché |
|---|---|
| L'immeuble a-t-il un contrat ? | `IMMEUBLE INCONNU` |
| Le fournisseur a-t-il un contrat pour cet immeuble ? | `FOURNISSEUR SANS CONTRAT` |
| La prestation figure-t-elle au contrat ? | `PRESTATION HORS CONTRAT` |
| Le prix unitaire HT correspond-il au tarif du contrat (avec la tolérance prévue) ? | `ÉCART DE PRIX` / `PRIX INFÉRIEUR` |
| La facture est-elle datée pendant la période de validité du contrat ? | `HORS PÉRIODE CONTRAT` |
| Quantité × prix unitaire = montant facturé ? | `ERREUR DE CALCUL` |
| Une prestation prévue au contrat n'a-t-elle jamais été facturée ? | `PRÉVUE NON FACTURÉE` |
| Tout est bon | `CONFORME` |

## Installation

```bash
pip install -r requirements.txt
```

## Utilisation

```bash
python -m controle_factures --contrats contrats.xlsx --factures factures.xlsx factures_pdf/ --sortie rapport.xlsx
```

- `--contrats` : un fichier CSV/Excel, ou un dossier qui en contient plusieurs (par exemple un fichier par copropriété).
- `--factures` : un ou plusieurs fichiers ou dossiers (CSV, Excel, PDF). Les sous-dossiers sont parcourus.
- `--sortie` : le rapport Excel produit (par défaut `rapport_controle_AAAA-MM-JJ.xlsx`).
- `--sans-non-facturees` : ne pas lister les prestations du contrat qui n'apparaissent pas dans les factures.

Essai avec les exemples fournis :

```bash
python -m controle_factures --contrats exemples/contrats.csv --factures exemples/factures.csv exemples/factures_pdf
```

## Le rapport Excel

- **Onglet « Synthèse »** : une ligne par immeuble (nombre de lignes, conformes, anomalies, total facturé,
  surcoût estimé) avec un lien vers l'onglet de l'immeuble, et la légende des statuts.
- **Un onglet par immeuble** : chaque ligne de facture à côté de la ligne de contrat correspondante
  (prix facturé, prix du contrat, écart en € et en %, commentaire), avec un code couleur et des filtres.
- **Onglet « Avertissements »** (s'il y en a) : PDF illisibles, etc.

Le *surcoût estimé* vaut : l'écart de prix × quantité pour un écart de prix ; le montant entier pour une
prestation hors contrat, un fournisseur sans contrat ou un immeuble inconnu ; la différence pour une erreur de calcul.

## Format des données

Le plus simple est de remplir **`modele_controle_factures.xlsx`** (onglets `Contrats` et `Factures`).
Les noms de colonnes sont reconnus sans tenir compte des accents ni des majuscules ; les montants peuvent
être écrits `1 234,56` ou `1234.56`, les dates `JJ/MM/AAAA`.

### Contrats (une ligne par prestation et par immeuble)

| Colonne | Obligatoire | Exemple |
|---|---|---|
| Immeuble | oui | Résidence Les Tilleuls |
| Adresse | non (sert à reconnaître l'immeuble dans les PDF) | 12 rue des Tilleuls 69003 Lyon |
| Fournisseur | conseillé | Ascenseurs Durand |
| Référence contrat | non | ASC-2024-017 |
| Prestation | oui | Entretien ascenseur |
| Mots-clés | non — autres libellés utilisés sur les factures, séparés par `\|` | Maintenance ascenseur\|Visite ascenseur |
| Prix unitaire HT | oui | 185,00 |
| Unité, Fréquence | non (informatif) | visite, mensuelle |
| Date début, Date fin | non | 01/01/2024, 31/12/2026 |
| Tolérance % | non (0 par défaut) — utile pour les révisions de prix/indexations | 2 |

### Factures (une ligne par ligne de facture)

| Colonne | Exemple |
|---|---|
| Immeuble | Résidence Les Tilleuls |
| Fournisseur | Net'Pro Services |
| N° facture | NP-5521 |
| Date | 31/10/2026 |
| Prestation | Ménage parties communes - octobre |
| Quantité | 1 |
| Prix unitaire HT | 445,00 |
| Montant HT | 445,00 |

Si le prix unitaire est absent, il est déduit de `Montant HT / Quantité`.

### Factures PDF

Les PDF « texte » (pas les scans) sont lus automatiquement :

- l'**immeuble** est déterminé par le nom du dossier qui contient le PDF (ex. `factures/Le Clos Fleuri/xxx.pdf`)
  ou, à défaut, par le nom ou l'adresse de l'immeuble trouvé dans le texte ;
- le **fournisseur** est le fournisseur sous contrat dont le nom apparaît dans le texte ;
- chaque ligne qui se termine par un montant est lue comme `libellé  quantité  prix unitaire  montant`.

Cette lecture est automatique et dépend de la mise en page du fournisseur : vérifiez les lignes issues d'un PDF
(colonne *Source* du rapport). Pour un PDF scanné, passez-le d'abord par un OCR ou saisissez la facture dans le tableau.

## Rapprochement des libellés

Les libellés de facture rarement identiques au contrat sont rapprochés par : égalité, inclusion
(« Maintenance ascenseur octobre » ⊃ « Maintenance ascenseur »), puis similarité de texte. Ajoutez des
**mots-clés** au contrat pour fiabiliser le rapprochement. Les noms d'immeubles sont comparés de façon stricte
(« Résidence des Lilas » n'est jamais rattachée à « Résidence Les Tilleuls »).

## Tests

```bash
python -m pytest
```
