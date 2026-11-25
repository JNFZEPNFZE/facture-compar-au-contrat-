"""Rapprochement de chaque ligne de facture avec le contrat de l'immeuble concerné."""

from __future__ import annotations

from difflib import SequenceMatcher

from . import modeles as m
from .modeles import LigneContrat, LigneFacture, Resultat
from .utils import normaliser

SEUIL_RAPPROCHEMENT = 0.75
TOLERANCE_CALCUL = 0.02  # € d'arrondi admis sur quantité × PU = montant

ORDRE = [m.IMMEUBLE_INCONNU, m.FOURNISSEUR_SANS_CONTRAT, m.HORS_CONTRAT, m.ECART_PRIX,
         m.HORS_PERIODE, m.ERREUR_CALCUL, m.PRIX_INFERIEUR, m.NON_FACTUREE, m.CONFORME]


def similarite(a: str, b: str) -> float:
    a, b = normaliser(a), normaliser(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if f" {a} " in f" {b} " or f" {b} " in f" {a} ":
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


MOTS_GENERIQUES = {"residence", "immeuble", "copropriete", "syndicat", "des", "les", "le", "la", "l",
                    "du", "de", "d", "copro", "sdc", "sas", "sarl", "sa", "eurl", "et", "services", "service"}
SEUIL_NOM = 0.85


def _nom_distinctif(nom: str) -> str:
    mots = [w for w in normaliser(nom).split() if w not in MOTS_GENERIQUES]
    return " ".join(mots) or normaliser(nom)


def _resoudre(nom: str, candidats: set[str]) -> str | None:
    """Associe un nom saisi (immeuble, fournisseur) au nom de référence le plus proche.

    Les mots génériques (« Résidence », « Les », « SARL »…) sont ignorés et le seuil est strict,
    pour ne jamais rattacher une facture au mauvais immeuble.
    """
    if not nom:
        return None
    cible = _nom_distinctif(nom)
    meilleur = max(candidats, key=lambda c: similarite(cible, _nom_distinctif(c)), default=None)
    if meilleur and similarite(cible, _nom_distinctif(meilleur)) >= SEUIL_NOM:
        return meilleur
    return None


def _score_prestation(facture: LigneFacture, contrat: LigneContrat) -> float:
    return max(similarite(facture.prestation, lib) for lib in contrat.libelles() if lib)


def comparer_ligne(f: LigneFacture, contrats: list[LigneContrat]) -> Resultat:
    immeuble = _resoudre(f.immeuble, {c.immeuble for c in contrats})
    if immeuble is None:
        return Resultat(f.immeuble or "(non identifié)", f.fournisseur, f, None, [m.IMMEUBLE_INCONNU],
                        surcout=f.montant_effectif,
                        commentaire="Aucun contrat pour cet immeuble")

    du_lieu = [c for c in contrats if c.immeuble == immeuble]
    candidats = du_lieu
    fournisseur = f.fournisseur
    if f.fournisseur:
        ref = _resoudre(f.fournisseur, {c.fournisseur for c in du_lieu})
        if ref is None:
            return Resultat(immeuble, f.fournisseur, f, None, [m.FOURNISSEUR_SANS_CONTRAT],
                            surcout=f.montant_effectif,
                            commentaire="Aucun contrat avec ce fournisseur pour cet immeuble")
        fournisseur = ref
        candidats = [c for c in du_lieu if c.fournisseur == ref]

    scores = sorted(((_score_prestation(f, c), c.actif_le(f.date), c) for c in candidats),
                    key=lambda t: (t[0], t[1]), reverse=True)
    if not scores or scores[0][0] < SEUIL_RAPPROCHEMENT:
        proche = f" (le plus proche : « {scores[0][2].prestation} »)" if scores and scores[0][0] > 0.4 else ""
        return Resultat(immeuble, fournisseur, f, None, [m.HORS_CONTRAT], surcout=f.montant_effectif,
                        commentaire="Prestation non prévue au contrat" + proche)

    contrat = scores[0][2]
    fournisseur = fournisseur or contrat.fournisseur
    statuts, notes = [], []
    res = Resultat(immeuble, fournisseur, f, contrat, statuts)

    if not contrat.actif_le(f.date):
        statuts.append(m.HORS_PERIODE)
        debut = contrat.date_debut.strftime("%d/%m/%Y") if contrat.date_debut else "…"
        fin = contrat.date_fin.strftime("%d/%m/%Y") if contrat.date_fin else "…"
        notes.append(f"Contrat valable du {debut} au {fin}")

    pu = f.pu_effectif
    if pu is not None and contrat.prix_unitaire_ht:
        res.ecart_unitaire = round(pu - contrat.prix_unitaire_ht, 2)
        res.ecart_pct = round(100 * res.ecart_unitaire / contrat.prix_unitaire_ht, 2)
        if res.ecart_pct > contrat.tolerance_pct + 1e-9:
            statuts.append(m.ECART_PRIX)
            res.surcout = round(res.ecart_unitaire * (f.quantite or 1.0), 2)
            notes.append(f"Facturé {pu:.2f} € au lieu de {contrat.prix_unitaire_ht:.2f} € HT")
        elif res.ecart_pct < -contrat.tolerance_pct - 1e-9:
            statuts.append(m.PRIX_INFERIEUR)
            notes.append("Prix inférieur au contrat (vérifier la prestation réalisée)")
    elif pu is None:
        notes.append("Prix non lisible sur la facture")

    if f.quantite is not None and f.prix_unitaire_ht is not None and f.montant_ht is not None:
        attendu = f.quantite * f.prix_unitaire_ht
        if abs(attendu - f.montant_ht) > TOLERANCE_CALCUL:
            statuts.append(m.ERREUR_CALCUL)
            notes.append(f"{f.quantite:g} × {f.prix_unitaire_ht:.2f} = {attendu:.2f} € ≠ {f.montant_ht:.2f} €")
            res.surcout = round(res.surcout + max(0.0, f.montant_ht - attendu), 2)

    if not statuts:
        statuts.append(m.CONFORME)
    statuts.sort(key=ORDRE.index)
    res.commentaire = " ; ".join(notes)
    return res


def comparer(factures: list[LigneFacture], contrats: list[LigneContrat],
             signaler_non_facturees: bool = True) -> list[Resultat]:
    resultats = [comparer_ligne(f, contrats) for f in factures]

    if signaler_non_facturees and factures:
        utilises = {id(r.contrat) for r in resultats if r.contrat is not None}
        dates = [f.date for f in factures if f.date]
        debut, fin = (min(dates), max(dates)) if dates else (None, None)
        immeubles_factures = {r.immeuble for r in resultats}
        for c in contrats:
            if id(c) in utilises or c.immeuble not in immeubles_factures:
                continue
            if debut and ((c.date_fin and c.date_fin < debut) or (c.date_debut and c.date_debut > fin)):
                continue
            resultats.append(Resultat(c.immeuble, c.fournisseur, None, c, [m.NON_FACTUREE],
                                      commentaire="Prestation prévue au contrat, absente des factures analysées"))

    return trier(resultats)


def trier(resultats: list[Resultat]) -> list[Resultat]:
    def cle(r: Resultat):
        f = r.facture
        return (normaliser(r.immeuble), normaliser(r.fournisseur),
                f is None, (f.date.isoformat() if f and f.date else ""), f.numero if f else "",
                ORDRE.index(r.statut_principal))
    return sorted(resultats, key=cle)
