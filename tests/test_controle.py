from datetime import date
from pathlib import Path

import pytest
from openpyxl import load_workbook

from controle_factures import charger_contrats, charger_factures, comparer, ecrire_rapport
from controle_factures import modeles as m
from controle_factures.chargement import decouper_ligne
from controle_factures.comparaison import comparer_ligne
from controle_factures.modeles import LigneContrat, LigneFacture
from controle_factures.utils import lire_nombre

EXEMPLES = Path(__file__).resolve().parent.parent / "exemples"

CONTRATS = [
    LigneContrat("Résidence Les Tilleuls", "Net'Pro Services", "Nettoyage parties communes", 420.0,
                 date_debut=date(2025, 1, 1), date_fin=date(2026, 12, 31), mots_cles=["Ménage parties communes"]),
    LigneContrat("Résidence Les Tilleuls", "Ascenseurs Durand", "Entretien ascenseur", 185.0, tolerance_pct=2),
]


def facture(prestation, pu, qte=1.0, montant=None, immeuble="Résidence Les Tilleuls",
            fournisseur="Net'Pro Services", jour=date(2026, 10, 31)):
    return LigneFacture(immeuble, fournisseur, "F1", jour, prestation, qte, pu,
                        montant if montant is not None else pu * qte)


@pytest.mark.parametrize("texte,attendu", [
    ("1 234,56 €", 1234.56), ("1.234,56", 1234.56), ("1,234.56", 1234.56), ("420", 420.0), ("", None),
])
def test_lire_nombre(texte, attendu):
    assert lire_nombre(texte) == attendu


def test_conforme_via_mot_cle():
    r = comparer_ligne(facture("Ménage parties communes - octobre", 420), CONTRATS)
    assert r.statuts == [m.CONFORME]


def test_ecart_de_prix_et_surcout():
    r = comparer_ligne(facture("Nettoyage parties communes", 445, qte=2), CONTRATS)
    assert m.ECART_PRIX in r.statuts
    assert r.surcout == 50.0


def test_tolerance_respectee():
    r = comparer_ligne(facture("Entretien ascenseur", 188, fournisseur="Ascenseurs Durand"), CONTRATS)
    assert r.statuts == [m.CONFORME]  # +1,6 % < 2 %


def test_hors_contrat():
    r = comparer_ligne(facture("Désinfection local poubelles", 120), CONTRATS)
    assert r.statuts == [m.HORS_CONTRAT]


def test_fournisseur_sans_contrat():
    r = comparer_ligne(facture("Débouchage", 280, fournisseur="Plomberie Martin"), CONTRATS)
    assert r.statuts == [m.FOURNISSEUR_SANS_CONTRAT]


def test_immeuble_proche_non_confondu():
    r = comparer_ligne(facture("Nettoyage parties communes", 420, immeuble="Résidence des Lilas"), CONTRATS)
    assert r.statuts == [m.IMMEUBLE_INCONNU]


def test_immeuble_ecrit_differemment():
    r = comparer_ligne(facture("Nettoyage parties communes", 420, immeuble="LES TILLEULS"), CONTRATS)
    assert r.immeuble == "Résidence Les Tilleuls"


def test_hors_periode():
    r = comparer_ligne(facture("Nettoyage parties communes", 420, jour=date(2027, 2, 1)), CONTRATS)
    assert r.statuts == [m.HORS_PERIODE]


def test_erreur_de_calcul():
    r = comparer_ligne(facture("Nettoyage parties communes", 420, qte=2, montant=900), CONTRATS)
    assert m.ERREUR_CALCUL in r.statuts


def test_prevue_non_facturee():
    res = comparer([facture("Nettoyage parties communes", 420)], CONTRATS)
    assert [r.contrat.prestation for r in res if r.statuts == [m.NON_FACTUREE]] == ["Entretien ascenseur"]


@pytest.mark.parametrize("ligne,attendu", [
    ("Maintenance chaufferie T4 2026     1    1 310,00    1 310,00", ("Maintenance chaufferie T4 2026", 1, 1310, 1310)),
    ("Remplacement circulateur 1 640,00 640,00", ("Remplacement circulateur", 1, 640, 640)),
    ("Taille des haies 30 45,00 1 350,00 €", ("Taille des haies", 30, 45, 1350)),
    ("Désignation Qté PU HT Montant HT", None),
])
def test_decouper_ligne_pdf(ligne, attendu):
    assert decouper_ligne(ligne) == attendu


def test_exemples_de_bout_en_bout(tmp_path):
    contrats = charger_contrats(EXEMPLES / "contrats.csv")
    factures, avertissements = charger_factures([EXEMPLES / "factures.csv", EXEMPLES / "factures_pdf"], contrats)
    assert not avertissements
    res = comparer(factures, contrats)
    sortie = ecrire_rapport(res, tmp_path / "rapport.xlsx")

    par_immeuble = {}
    for r in res:
        par_immeuble.setdefault(r.immeuble, []).append(r.statut_principal)
    assert sorted(par_immeuble["Les Terrasses du Parc"]) == sorted([m.HORS_CONTRAT, m.ECART_PRIX, m.CONFORME])
    assert par_immeuble["Résidence des Lilas"] == [m.IMMEUBLE_INCONNU]

    wb = load_workbook(sortie)
    assert wb.sheetnames[0] == "Synthèse"
    assert set(wb.sheetnames[1:]) == set(par_immeuble)
