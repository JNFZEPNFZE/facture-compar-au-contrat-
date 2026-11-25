"""Fonctions utilitaires : lecture de tableaux (CSV / Excel), normalisation, nombres, dates."""

from __future__ import annotations

import csv
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path


def normaliser(texte: str | None) -> str:
    """Minuscules, sans accents ni ponctuation, espaces simplifiés."""
    if texte is None:
        return ""
    texte = unicodedata.normalize("NFKD", str(texte))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = re.sub(r"[^a-z0-9]+", " ", texte.lower())
    return texte.strip()


def lire_nombre(valeur) -> float | None:
    """Convertit '1 234,56 €', '1234.56', 1234.56 ... en float. None si vide."""
    if valeur is None:
        return None
    if isinstance(valeur, (int, float)):
        return float(valeur)
    s = str(valeur).strip()
    if not s:
        return None
    s = s.replace(" ", "").replace(" ", "").replace(" ", "")
    s = s.replace("€", "").replace("EUR", "").replace("%", "")
    if "," in s and "." in s:
        # 1.234,56 (FR) ou 1,234.56 (EN) : le dernier séparateur est la décimale
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        raise ValueError(f"Nombre illisible : {valeur!r}") from None


def lire_date(valeur) -> date | None:
    if valeur is None or valeur == "":
        return None
    if isinstance(valeur, datetime):
        return valeur.date()
    if isinstance(valeur, date):
        return valeur
    s = str(valeur).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Date illisible : {valeur!r} (attendu JJ/MM/AAAA)")


def lire_tableau(chemin: Path, feuille: str | None = None) -> list[dict]:
    """Lit un CSV (séparateur ; ou ,) ou un classeur Excel.

    Renvoie une liste de dictionnaires dont les clés sont les en-têtes normalisés.
    """
    chemin = Path(chemin)
    suffixe = chemin.suffix.lower()
    if suffixe in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook

        wb = load_workbook(chemin, data_only=True, read_only=True)
        ws = wb[feuille] if feuille and feuille in wb.sheetnames else wb.worksheets[0]
        lignes = list(ws.iter_rows(values_only=True))
        wb.close()
    elif suffixe in (".csv", ".txt"):
        texte = chemin.read_text(encoding="utf-8-sig")
        premiere = texte.splitlines()[0] if texte else ""
        sep = ";" if premiere.count(";") >= premiere.count(",") else ","
        lignes = list(csv.reader(texte.splitlines(), delimiter=sep))
    else:
        raise ValueError(f"Format non pris en charge : {chemin.name} (CSV ou XLSX attendu)")

    if not lignes:
        return []
    entetes = [normaliser(h) for h in lignes[0]]
    resultat = []
    for num, ligne in enumerate(lignes[1:], start=2):
        if ligne is None or all(v is None or str(v).strip() == "" for v in ligne):
            continue
        d = {entetes[i]: ligne[i] for i in range(min(len(entetes), len(ligne))) if entetes[i]}
        d["_ligne"] = num
        resultat.append(d)
    return resultat


def champ(d: dict, *noms, defaut=None):
    """Récupère la première colonne présente parmi plusieurs intitulés possibles."""
    for nom in noms:
        v = d.get(normaliser(nom))
        if v is not None and str(v).strip() != "":
            return v.strip() if isinstance(v, str) else v
    return defaut
