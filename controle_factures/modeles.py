"""Structures de données : lignes de contrat, lignes de facture, résultats de contrôle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .utils import normaliser


@dataclass
class LigneContrat:
    immeuble: str
    fournisseur: str
    prestation: str
    prix_unitaire_ht: float
    unite: str = ""
    frequence: str = ""
    date_debut: date | None = None
    date_fin: date | None = None
    tolerance_pct: float = 0.0
    mots_cles: list[str] = field(default_factory=list)
    reference_contrat: str = ""
    adresse: str = ""

    def libelles(self) -> list[str]:
        """Libellé + mots-clés, normalisés, pour le rapprochement."""
        return [normaliser(self.prestation)] + [normaliser(m) for m in self.mots_cles if m]

    def actif_le(self, jour: date | None) -> bool:
        if jour is None:
            return True
        if self.date_debut and jour < self.date_debut:
            return False
        if self.date_fin and jour > self.date_fin:
            return False
        return True


@dataclass
class LigneFacture:
    immeuble: str
    fournisseur: str
    numero: str
    date: date | None
    prestation: str
    quantite: float | None
    prix_unitaire_ht: float | None
    montant_ht: float | None
    source: str = ""  # fichier d'origine

    @property
    def pu_effectif(self) -> float | None:
        """Prix unitaire facturé ; déduit du montant / quantité s'il manque."""
        if self.prix_unitaire_ht is not None:
            return self.prix_unitaire_ht
        if self.montant_ht is not None:
            q = self.quantite if self.quantite else 1.0
            return self.montant_ht / q
        return None

    @property
    def montant_effectif(self) -> float:
        if self.montant_ht is not None:
            return self.montant_ht
        if self.prix_unitaire_ht is not None:
            return self.prix_unitaire_ht * (self.quantite or 1.0)
        return 0.0


# Statuts possibles, du plus grave au moins grave
IMMEUBLE_INCONNU = "IMMEUBLE INCONNU"
FOURNISSEUR_SANS_CONTRAT = "FOURNISSEUR SANS CONTRAT"
HORS_CONTRAT = "PRESTATION HORS CONTRAT"
ECART_PRIX = "ÉCART DE PRIX"
HORS_PERIODE = "HORS PÉRIODE CONTRAT"
ERREUR_CALCUL = "ERREUR DE CALCUL"
PRIX_INFERIEUR = "PRIX INFÉRIEUR"
CONFORME = "CONFORME"
NON_FACTUREE = "PRÉVUE NON FACTURÉE"

ANOMALIES = {IMMEUBLE_INCONNU, FOURNISSEUR_SANS_CONTRAT, HORS_CONTRAT, ECART_PRIX, HORS_PERIODE, ERREUR_CALCUL}


@dataclass
class Resultat:
    immeuble: str
    fournisseur: str
    facture: LigneFacture | None
    contrat: LigneContrat | None
    statuts: list[str]
    ecart_unitaire: float | None = None
    ecart_pct: float | None = None
    surcout: float = 0.0
    commentaire: str = ""

    @property
    def statut_principal(self) -> str:
        return self.statuts[0] if self.statuts else CONFORME

    @property
    def est_anomalie(self) -> bool:
        return any(s in ANOMALIES for s in self.statuts)
