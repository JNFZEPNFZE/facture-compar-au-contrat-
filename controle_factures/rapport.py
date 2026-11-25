"""Rapport Excel : une synthèse, puis un onglet par immeuble."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import modeles as m
from .modeles import Resultat

COULEURS = {
    m.IMMEUBLE_INCONNU: "F4B6B6",
    m.FOURNISSEUR_SANS_CONTRAT: "F4B6B6",
    m.HORS_CONTRAT: "F4B6B6",
    m.ECART_PRIX: "F8CBAD",
    m.HORS_PERIODE: "FFE699",
    m.ERREUR_CALCUL: "FFE699",
    m.PRIX_INFERIEUR: "DDEBF7",
    m.NON_FACTUREE: "EDEDED",
    m.CONFORME: "C6EFCE",
}
EN_TETE = PatternFill("solid", fgColor="1F3864")
GRAS_BLANC = Font(bold=True, color="FFFFFF")
FIN = Side(style="thin", color="BFBFBF")
BORDURE = Border(left=FIN, right=FIN, top=FIN, bottom=FIN)
EUROS = '#,##0.00 "€"'
POURCENT = '0.0" %"'

COLONNES_DETAIL = [
    ("Statut", 26), ("Fournisseur", 22), ("N° facture", 14), ("Date", 11), ("Prestation facturée", 34),
    ("Prestation contrat", 34), ("Qté", 7), ("PU facturé HT", 13), ("PU contrat HT", 13),
    ("Écart unitaire", 12), ("Écart %", 9), ("Tolérance %", 10), ("Montant HT", 13),
    ("Surcoût estimé", 13), ("Commentaire", 50), ("Source", 22),
]


def _entete(ws, colonnes, ligne=1):
    for i, (titre, largeur) in enumerate(colonnes, start=1):
        c = ws.cell(row=ligne, column=i, value=titre)
        c.fill, c.font, c.border = EN_TETE, GRAS_BLANC, BORDURE
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = largeur
    ws.freeze_panes = ws.cell(row=ligne + 1, column=1)


def _nom_onglet(nom: str, pris: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", "-", nom)[:31] or "Immeuble"
    nom_final, i = base, 2
    while nom_final.lower() in pris:
        suffixe = f" ({i})"
        nom_final, i = base[: 31 - len(suffixe)] + suffixe, i + 1
    pris.add(nom_final.lower())
    return nom_final


def _ligne_detail(r: Resultat) -> list:
    f, c = r.facture, r.contrat
    return [
        " + ".join(r.statuts),
        r.fournisseur or (c.fournisseur if c else ""),
        f.numero if f else "",
        f.date if f else None,
        f.prestation if f else "",
        c.prestation if c else "",
        f.quantite if f else None,
        f.pu_effectif if f else None,
        c.prix_unitaire_ht if c else None,
        r.ecart_unitaire,
        r.ecart_pct,
        c.tolerance_pct if c else None,
        f.montant_effectif if f else None,
        r.surcout or None,
        r.commentaire,
        f.source if f else (f"Contrat {c.reference_contrat}".strip() if c else ""),
    ]


def ecrire_rapport(resultats: list[Resultat], sortie: Path, avertissements: list[str] | None = None) -> Path:
    wb = Workbook()
    synthese = wb.active
    synthese.title = "Synthèse"

    par_immeuble: dict[str, list[Resultat]] = defaultdict(list)
    for r in resultats:
        par_immeuble[r.immeuble].append(r)

    # ---- Synthèse
    synthese["A1"] = "Contrôle des factures au regard des contrats — synthèse par immeuble"
    synthese["A1"].font = Font(bold=True, size=14)
    cols = [("Immeuble", 30), ("Lignes facturées", 12), ("Conformes", 11), ("Anomalies", 11),
            ("Hors contrat", 11), ("Écarts de prix", 11), ("Prévues non facturées", 12),
            ("Total facturé HT", 15), ("Surcoût estimé HT", 15), ("Onglet", 24)]
    _entete(synthese, cols, ligne=3)

    pris = {"synthèse", "avertissements"}
    ligne = 4
    for immeuble in sorted(par_immeuble, key=str.lower):
        rs = par_immeuble[immeuble]
        factures = [r for r in rs if r.facture]
        onglet = _nom_onglet(immeuble, pris)
        valeurs = [
            immeuble,
            len(factures),
            sum(1 for r in factures if not r.est_anomalie),
            sum(1 for r in factures if r.est_anomalie),
            sum(1 for r in factures if r.statut_principal in (m.HORS_CONTRAT, m.FOURNISSEUR_SANS_CONTRAT, m.IMMEUBLE_INCONNU)),
            sum(1 for r in factures if m.ECART_PRIX in r.statuts),
            sum(1 for r in rs if r.facture is None),
            round(sum(r.facture.montant_effectif for r in factures), 2),
            round(sum(r.surcout for r in factures), 2),
            onglet,
        ]
        for j, v in enumerate(valeurs, start=1):
            cell = synthese.cell(row=ligne, column=j, value=v)
            cell.border = BORDURE
            if j in (8, 9):
                cell.number_format = EUROS
        lien = synthese.cell(row=ligne, column=10)
        lien.hyperlink = f"#'{onglet}'!A1"
        lien.font = Font(color="0563C1", underline="single")
        etat = synthese.cell(row=ligne, column=1)
        etat.fill = PatternFill("solid", fgColor=COULEURS[m.CONFORME] if valeurs[3] == 0 else COULEURS[m.ECART_PRIX])

        # ---- Onglet de l'immeuble
        ws = wb.create_sheet(onglet)
        ws["A1"] = immeuble
        ws["A1"].font = Font(bold=True, size=14)
        adresse = next((r.contrat.adresse for r in rs if r.contrat and r.contrat.adresse), "")
        ws["A2"] = f"{adresse}  —  {valeurs[3]} anomalie(s) sur {valeurs[1]} ligne(s), surcoût estimé {valeurs[8]:.2f} € HT".strip(" —")
        _entete(ws, COLONNES_DETAIL, ligne=4)
        for i, r in enumerate(rs, start=5):
            remplissage = PatternFill("solid", fgColor=COULEURS[r.statut_principal])
            for j, v in enumerate(_ligne_detail(r), start=1):
                cell = ws.cell(row=i, column=j, value=v)
                cell.border = BORDURE
                cell.alignment = Alignment(vertical="top", wrap_text=j in (5, 6, 15))
                if j == 1:
                    cell.fill = remplissage
                    cell.font = Font(bold=True)
                elif j == 4:
                    cell.number_format = "DD/MM/YYYY"
                elif j in (8, 9, 10, 13, 14):
                    cell.number_format = EUROS
                elif j in (11, 12):
                    cell.number_format = POURCENT
        ws.auto_filter.ref = f"A4:{get_column_letter(len(COLONNES_DETAIL))}{max(5, 4 + len(rs))}"
        ligne += 1

    # Totaux
    if ligne > 4:
        synthese.cell(row=ligne, column=1, value="TOTAL").font = Font(bold=True)
        for j in range(2, 10):
            col = get_column_letter(j)
            c = synthese.cell(row=ligne, column=j, value=f"=SUM({col}4:{col}{ligne - 1})")
            c.font = Font(bold=True)
            c.border = BORDURE
            if j in (8, 9):
                c.number_format = EUROS

    # Légende
    leg = ligne + 2
    synthese.cell(row=leg, column=1, value="Légende des statuts").font = Font(bold=True)
    explications = {
        m.IMMEUBLE_INCONNU: "Aucun contrat trouvé pour l'immeuble indiqué sur la facture",
        m.FOURNISSEUR_SANS_CONTRAT: "Le fournisseur n'a pas de contrat pour cet immeuble",
        m.HORS_CONTRAT: "Prestation facturée qui ne figure pas au contrat",
        m.ECART_PRIX: "Prix unitaire supérieur au tarif du contrat (au-delà de la tolérance)",
        m.HORS_PERIODE: "Facture datée en dehors de la période de validité du contrat",
        m.ERREUR_CALCUL: "Quantité × prix unitaire ≠ montant facturé",
        m.PRIX_INFERIEUR: "Prix inférieur au contrat : vérifier que la prestation a été entièrement réalisée",
        m.NON_FACTUREE: "Prestation prévue au contrat mais absente des factures analysées",
        m.CONFORME: "Tarif et prestation conformes au contrat",
    }
    for k, (statut, texte) in enumerate(explications.items(), start=leg + 1):
        c = synthese.cell(row=k, column=1, value=statut)
        c.fill = PatternFill("solid", fgColor=COULEURS[statut])
        synthese.cell(row=k, column=2, value=texte)

    if avertissements:
        ws = wb.create_sheet("Avertissements")
        _entete(ws, [("Avertissement", 120)])
        for i, a in enumerate(avertissements, start=2):
            ws.cell(row=i, column=1, value=a)

    sortie = Path(sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    wb.save(sortie)
    return sortie
