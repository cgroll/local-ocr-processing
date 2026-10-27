"""One-off: assemble a representative ~20-document subset of the EEP RVA sample into data/raw/ and
write data/eep_manifest.csv. Not part of the shipped pipeline -- a convenience for local runs.

Covers all three document types (Doku/datasheet/manual, R&I diagram, Stromlaufplan/schematic), all
ten plant sections, and the full size range (1 to 452 pages). The "Legende der Symbole" sheet is
identical across four sections, so it is included only once.

Run with the EEP venv (has pymupdf) or this project's:
    python -I scripts/build_eep_subset.py
"""
import csv
import shutil
from pathlib import Path

import pymupdf

SRC = Path.home() / "repos/EEP/data/RVA_Sample"
RAW = Path("data/raw")
MANIFEST = Path("data/eep_manifest.csv")

# (id, section-folder, filename, group, tags)
# `group` is constrained by the manifest validator to datasheet/report/scan/corpus-sample, so the
# RVA document type is carried in `tags` instead: datasheet -> datasheet, Betriebsanleitung/manual
# -> report, R&I diagrams and Stromlauf schematics (scanned/vector) -> scan.
SEL = [
    ("eep-01-kessel-doku", "01_Kessel", "Doku__RVA_R2HLB10AN001 Fluidisierungsgebläse M3BP355SMB2 250kW B3 Datenblatt.pdf", "datasheet", "datasheet"),
    ("eep-02-dampf-doku", "02_Dampf", "Doku__R2MKA10_Datenblatt Generator.pdf", "datasheet", "datasheet"),
    ("eep-05-rohr-doku", "05_Rohrleitungen", "Doku__R2GHB70AA505_AK DeiLtg hi RohReinKonWT_Bedienungsanleitung_Rev0.pdf", "report", "manual"),
    ("eep-07-rueckkuehler-doku", "07_Rueckkuehler", "Doku__RVA_R2PGD91AC001_RüKü_Technisches Datenblatt_Rev01.pdf", "datasheet", "datasheet;table"),
    ("eep-08-ve-doku", "08_VE-Anlage", "Doku__R2GCK30CQ001_LF hi KaDeiPp_Betriebsanleitung Messumformer.pdf", "report", "manual"),
    ("eep-09-schlamm-doku", "09_Schlammentwaesserung", "Doku__R2EMC05AP005_Betriebsanleitung Konzentratpumpe 1.pdf", "report", "manual"),
    ("eep-10-hkl-doku", "10_Heizung-HKL", "Doku__RVA_R2SBM05BE001_Schmutzfänger_Datenblatt_Rev0.pdf", "datasheet", "datasheet"),
    ("eep-02-dampf-ri-legende", "02_Dampf", "R&I__RVA.EPC.000.FB000_06 R&I - Legende der Symbole 1v2.pdf", "scan", "legend;diagram"),
    ("eep-01-kessel-ri", "01_Kessel", "R&I__C-01-846288-088-0003-017-REV05_R und I Schemata.pdf", "scan", "diagram"),
    ("eep-04-leit-ri", "04_Leittechnik", "R&I__RVA.EPC.XXX.FB0XX_07 R&Is all.pdf", "scan", "diagram"),
    ("eep-05-rohr-ri", "05_Rohrleitungen", "R&I__RVA.EPC.XXX.FB0XX_06 R&Is all.pdf", "scan", "diagram"),
    ("eep-10-hkl-ri", "10_Heizung-HKL", "R&I__RVA_R&I_Schema_Rev0.pdf", "scan", "diagram"),
    ("eep-03-brennstoff-ri", "03_Brennstoffversorgung", "R&I__R2EAB10AB001_Dock-Stat 1_R&I_TDS_1_Rev0.pdf", "scan", "diagram"),
    ("eep-01-kessel-strom", "01_Kessel", "Stromlaufplan__RVA_R2HLB10AN001_Schaltplan für Überwachung.pdf", "scan", "schematic"),
    ("eep-02-dampf-strom", "02_Dampf", "Stromlaufplan__R2MKA10_Schaltplan.pdf", "scan", "schematic"),
    ("eep-06-druckluft-strom", "06_Druck-Steuerluft", "Stromlaufplan__R2QFA10AN001_Schaltplan S160-4LF_Rev0.pdf", "scan", "schematic"),
    ("eep-07-rueckkuehler-strom", "07_Rueckkuehler", "Stromlaufplan__RVA_R2PGD91GH010_Stromlaufplan_Rev02.pdf", "scan", "schematic"),
    ("eep-08-ve-strom", "08_VE-Anlage", "Stromlaufplan__R2GCK30AH010_RoHz PpHs z KaDeiTk _Stromlaufplan.pdf", "scan", "schematic"),
    ("eep-09-schlamm-strom", "09_Schlammentwaesserung", "Stromlaufplan__RVA.HIL-SAT.23-1219_Schaltplan_REV25-06-06.pdf", "scan", "schematic"),
    ("eep-10-hkl-strom", "10_Heizung-HKL", "Stromlaufplan__RVA_R2SBM05GS001_Schaltplan Wärmeübergabestation_Rev0.pdf", "scan", "schematic"),
]

COLS = ["id", "url", "group", "rights", "rights_source", "tags", "title", "kind", "pages", "page_range", "sha256", "notes"]


def main() -> None:
    rows = []
    for did, sec, fn, group, tags in SEL:
        src = SRC / sec / fn
        if not src.exists():
            raise SystemExit(f"missing source: {src}")
        dst = RAW / did / "document.pdf"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        with pymupdf.open(dst) as d:
            n = d.page_count
        rows.append({
            "id": did, "url": "file://eep-rva-sample", "group": group, "rights": "vendor-copyright",
            "rights_source": "EEP RVA sample, internal, local use only", "tags": tags,
            "title": fn.split("__", 1)[-1].rsplit(".pdf", 1)[0][:70], "kind": "native",
            "pages": str(n), "page_range": f"1-{min(6, n)}", "sha256": "", "notes": "EEP subset",
        })
        print(f"  {did}: {n}p")
    with open(MANIFEST, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    in_scope = sum(int(r["page_range"].split("-")[1]) for r in rows)
    print(f"\n{len(rows)} documents, {sum(int(r['pages']) for r in rows)} pages total, {in_scope} pages in scope")
    print("manifest:", MANIFEST)


if __name__ == "__main__":
    main()
