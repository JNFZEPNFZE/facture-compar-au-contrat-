"""Chargement des contrats et des factures (tableaux CSV/Excel ou PDF)."""

from __future__ import annotations

import re
from pathlib import Path

from .modeles import LigneContrat, LigneFacture
from .utils import champ, lire_date, lire_nombre, lire_tableau, normaliser


class ErreurDonnees(Exception):
    pass


def _contexte(fichier: Path, ligne: dict) -> str:
    return f"{fichier.name}, ligne {ligne.get('_ligne', '?')}"


# --------------------------------------------------------------------------- contrats

def charger_contrats(chemin: Path) -> list[LigneContrat]:
    """Charge un fichier de contrats, ou tous les CSV/XLSX d'un dossier."""
    chemin = Path(chemin)
    fichiers = _lister(chemin, (".csv", ".xlsx", ".xlsm"))
    contrats: list[LigneContrat] = []
    for f in fichiers:
        for d in lire_tableau(f, feuille="Contrats"):
            try:
                immeuble = champ(d, "Immeuble", "Copropriété", "Copropriete", "Résidence")
                prestation = champ(d, "Prestation", "Désignation", "Libellé")
                prix = lire_nombre(champ(d, "Prix unitaire HT", "PU HT", "Prix HT", "Tarif HT", "Tarif"))
                if not immeuble or not prestation or prix is None:
                    raise ErreurDonnees("colonnes Immeuble, Prestation et Prix unitaire HT obligatoires")
                mots = champ(d, "Mots-clés", "Mots clés", "Alias", defaut="") or ""
                contrats.append(
                    LigneContrat(
                        immeuble=str(immeuble),
                        fournisseur=str(champ(d, "Fournisseur", "Prestataire", defaut="")),
                        prestation=str(prestation),
                        prix_unitaire_ht=prix,
                        unite=str(champ(d, "Unité", "Unite", defaut="")),
                        frequence=str(champ(d, "Fréquence", "Frequence", "Périodicité", defaut="")),
                        date_debut=lire_date(champ(d, "Date début", "Début", "Date de début")),
                        date_fin=lire_date(champ(d, "Date fin", "Fin", "Date de fin")),
                        tolerance_pct=lire_nombre(champ(d, "Tolérance %", "Tolérance", "Tolerance")) or 0.0,
                        mots_cles=[m.strip() for m in re.split(r"[|;]", str(mots)) if m.strip()],
                        reference_contrat=str(champ(d, "Référence contrat", "N° contrat", "Contrat", defaut="")),
                        adresse=str(champ(d, "Adresse", defaut="")),
                    )
                )
            except (ValueError, ErreurDonnees) as e:
                raise ErreurDonnees(f"Contrat {_contexte(f, d)} : {e}") from None
    if not contrats:
        raise ErreurDonnees(f"Aucune ligne de contrat trouvée dans {chemin}")
    return contrats


# --------------------------------------------------------------------------- factures (tableaux)

def charger_factures_tableau(fichier: Path) -> list[LigneFacture]:
    lignes = []
    for d in lire_tableau(fichier, feuille="Factures"):
        try:
            lignes.append(
                LigneFacture(
                    immeuble=str(champ(d, "Immeuble", "Copropriété", "Copropriete", "Résidence", defaut="")),
                    fournisseur=str(champ(d, "Fournisseur", "Prestataire", defaut="")),
                    numero=str(champ(d, "N° facture", "Numéro facture", "Facture", "Numero", defaut="")),
                    date=lire_date(champ(d, "Date", "Date facture")),
                    prestation=str(champ(d, "Prestation", "Désignation", "Libellé", defaut="")),
                    quantite=lire_nombre(champ(d, "Quantité", "Quantite", "Qté", "Qte")),
                    prix_unitaire_ht=lire_nombre(champ(d, "Prix unitaire HT", "PU HT", "Prix HT")),
                    montant_ht=lire_nombre(champ(d, "Montant HT", "Total HT", "Montant")),
                    source=fichier.name,
                )
            )
        except ValueError as e:
            raise ErreurDonnees(f"Facture {_contexte(fichier, d)} : {e}") from None
    return lignes


# --------------------------------------------------------------------------- factures (PDF)

_JETON_NOMBRE = re.compile(r"-?\d+(?:[.,]\d+)*")
_DATE = re.compile(r"\b(\d{2}[/.-]\d{2}[/.-]\d{4})\b")
_NUMERO = re.compile(r"facture\s*(?:n\s*[°o]|no|num[ée]ro)?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/_]{2,})", re.I)
_EXCLUS = ("total", "tva", "net a payer", "acompte", "solde", "iban", "bic", "siret", "capital",
           "echeance", "reglement", "remise", "page", "rcs", "ttc", "sous total", "date")


def _groupements(jetons: list[str], n: int) -> list[tuple[list[float], int]]:
    """Toutes les façons de lire les derniers jetons comme n nombres.

    Gère les milliers séparés par des espaces (« 1 310,00 »). Renvoie (nombres, nb de jetons consommés).
    """
    if n == 0:
        return [([], 0)]
    res = []
    for k in range(1, min(len(jetons), 5) + 1):  # un nombre = 1 à 5 jetons
        groupe = jetons[len(jetons) - k:]
        if k > 1 and not (re.fullmatch(r"-?\d{1,3}", groupe[0])
                          and all(re.fullmatch(r"\d{3}", g) for g in groupe[1:-1])
                          and re.fullmatch(r"\d{3}(?:[.,]\d{1,2})?", groupe[-1])):
            continue
        try:
            valeur = lire_nombre("".join(groupe))
        except ValueError:
            continue
        for avant, conso in _groupements(jetons[: len(jetons) - k], n - 1):
            res.append((avant + [valeur], conso + k))
    return res


def decouper_ligne(brut: str) -> tuple[str, float | None, float | None, float] | None:
    """Sépare une ligne de facture en (libellé, quantité, PU, montant).

    Choisit la lecture la plus cohérente : quantité × PU = montant si possible.
    """
    jetons = [j for j in brut.replace("€", " ").split() if j]
    fin = len(jetons)
    while fin and _JETON_NOMBRE.fullmatch(jetons[fin - 1]):
        fin -= 1
    libelle_jetons, queue = jetons[:fin], jetons[fin:]
    if not queue or not re.search(r"[.,]\d{2}$", queue[-1]):
        return None  # pas de montant en fin de ligne

    meilleur = None  # (score, jetons consommés, (qte, pu, montant), conso)
    for n in (3, 2, 1):
        for nombres, conso in _groupements(queue, n):
            if n == 3:
                q, pu, mt = nombres
                if abs(q * pu - mt) > 0.02:
                    continue
                score, valeurs = 3, (q, pu, mt)
            elif n == 2:
                a, mt = nombres
                if abs(a - mt) <= 0.02:
                    score, valeurs = 2, (1.0, a, mt)
                elif a and float(a).is_integer() and a < 1000:
                    score, valeurs = 1, (a, None, mt)
                else:
                    continue
            else:
                score, valeurs = 0, (1.0, None, nombres[0])
            cand = (score, conso, valeurs)
            if meilleur is None or cand[:2] > meilleur[:2]:
                meilleur = cand
    if meilleur is None:
        return None
    _, conso, (q, pu, mt) = meilleur
    libelle = " ".join(libelle_jetons + queue[: len(queue) - conso]).strip(" -:")
    if len(normaliser(libelle)) < 3:
        return None
    return libelle, q, pu, mt


def _trouver(texte_norm: str, candidats: dict[str, list[str]]) -> str | None:
    """Renvoie la clé dont l'un des libellés normalisés apparaît dans le texte (le plus long gagne)."""
    meilleur, longueur = None, 0
    for cle, libelles in candidats.items():
        for lib in libelles:
            if lib and len(lib) > longueur and re.search(rf"\b{re.escape(lib)}\b", texte_norm):
                meilleur, longueur = cle, len(lib)
    return meilleur


def charger_facture_pdf(fichier: Path, contrats: list[LigneContrat]) -> list[LigneFacture]:
    """Lecture « au mieux » d'une facture PDF texte (non scannée).

    - Immeuble : nom du dossier parent s'il correspond à un immeuble, sinon nom/adresse trouvé dans le texte.
    - Fournisseur : nom d'un fournisseur sous contrat trouvé dans le texte.
    - Lignes : toute ligne contenant un montant ; rapprochée d'une prestation du contrat si possible.
    """
    import pdfplumber

    with pdfplumber.open(fichier) as pdf:
        texte = "\n".join((p.extract_text() or "") for p in pdf.pages)
    if not texte.strip():
        raise ErreurDonnees(f"{fichier.name} : aucun texte lisible (PDF scanné ? passer par un OCR ou saisir la facture dans le tableau)")
    texte_norm = normaliser(texte)

    immeubles = {}
    for c in contrats:
        immeubles.setdefault(c.immeuble, set()).update({normaliser(c.immeuble), normaliser(c.adresse)})
    immeubles = {k: [v for v in vs if v] for k, vs in immeubles.items()}
    immeuble = _trouver(normaliser(fichier.parent.name), immeubles) or _trouver(texte_norm, immeubles) or ""

    fournisseurs = {c.fournisseur: [normaliser(c.fournisseur)] for c in contrats if not immeuble or c.immeuble == immeuble}
    fournisseur = _trouver(texte_norm, fournisseurs) or ""

    m = _NUMERO.search(texte)
    numero = m.group(1) if m else fichier.stem
    m = _DATE.search(texte)
    date = lire_date(m.group(1).replace(".", "/").replace("-", "/")) if m else None

    lignes = []
    for brut in texte.splitlines():
        ligne_norm = normaliser(brut)
        if not ligne_norm or any(re.search(rf"\b{x}\b", ligne_norm) for x in _EXCLUS):
            continue
        if _DATE.search(brut):
            continue
        decoupe = decouper_ligne(brut)
        if decoupe is None:
            continue
        libelle, qte, pu, montant = decoupe
        lignes.append(LigneFacture(immeuble, fournisseur, numero, date, libelle, qte, pu, montant,
                                   source=f"{fichier.name} (PDF)"))
    return lignes


# --------------------------------------------------------------------------- point d'entrée

def _lister(chemin: Path, extensions: tuple[str, ...]) -> list[Path]:
    if chemin.is_file():
        return [chemin]
    if chemin.is_dir():
        return sorted(p for p in chemin.rglob("*") if p.suffix.lower() in extensions and not p.name.startswith("~$"))
    raise ErreurDonnees(f"Introuvable : {chemin}")


def charger_factures(chemins: list[Path], contrats: list[LigneContrat]) -> tuple[list[LigneFacture], list[str]]:
    """Charge des factures depuis des fichiers ou dossiers (CSV, XLSX, PDF). Renvoie (lignes, avertissements)."""
    lignes, avertissements = [], []
    for chemin in chemins:
        for f in _lister(Path(chemin), (".csv", ".xlsx", ".xlsm", ".pdf")):
            if f.suffix.lower() == ".pdf":
                try:
                    lu = charger_facture_pdf(f, contrats)
                    if not lu:
                        avertissements.append(f"{f.name} : aucune ligne de prestation détectée")
                    lignes.extend(lu)
                except ErreurDonnees as e:
                    avertissements.append(str(e))
            else:
                lignes.extend(charger_factures_tableau(f))
    return lignes, avertissements
