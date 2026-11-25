"""Ligne de commande :

    python -m controle_factures --contrats contrats.xlsx --factures factures/ --sortie rapport.xlsx
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from .chargement import ErreurDonnees, charger_contrats, charger_factures
from .comparaison import comparer
from .rapport import ecrire_rapport


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="controle_factures",
        description="Compare chaque facture au contrat de la copropriété concernée et produit un rapport Excel trié par immeuble.",
    )
    p.add_argument("--contrats", required=True, type=Path, help="Fichier (CSV/XLSX) ou dossier des contrats")
    p.add_argument("--factures", required=True, type=Path, nargs="+", help="Fichiers ou dossiers de factures (CSV, XLSX, PDF)")
    p.add_argument("--sortie", type=Path, default=Path(f"rapport_controle_{date.today():%Y-%m-%d}.xlsx"),
                   help="Fichier Excel de sortie")
    p.add_argument("--sans-non-facturees", action="store_true",
                   help="Ne pas lister les prestations du contrat absentes des factures")
    args = p.parse_args(argv)

    try:
        contrats = charger_contrats(args.contrats)
        factures, avertissements = charger_factures(args.factures, contrats)
    except ErreurDonnees as e:
        print(f"Erreur : {e}", file=sys.stderr)
        return 2

    if not factures:
        print("Aucune ligne de facture trouvée.", file=sys.stderr)
        for a in avertissements:
            print(f"  ! {a}", file=sys.stderr)
        return 1

    resultats = comparer(factures, contrats, signaler_non_facturees=not args.sans_non_facturees)
    sortie = ecrire_rapport(resultats, args.sortie, avertissements)

    print(f"{len(contrats)} ligne(s) de contrat, {len(factures)} ligne(s) de facture analysées.\n")
    immeubles = sorted({r.immeuble for r in resultats}, key=str.lower)
    for imm in immeubles:
        rs = [r for r in resultats if r.immeuble == imm and r.facture]
        anomalies = [r for r in rs if r.est_anomalie]
        surcout = sum(r.surcout for r in rs)
        marque = "OK " if not anomalies else "!! "
        print(f"{marque}{imm} : {len(rs)} ligne(s), {len(anomalies)} anomalie(s), surcoût estimé {surcout:.2f} € HT")
        for statut, n in Counter(r.statut_principal for r in anomalies).most_common():
            print(f"      - {statut} : {n}")
    for a in avertissements:
        print(f"  ! {a}")
    print(f"\nRapport : {sortie.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
