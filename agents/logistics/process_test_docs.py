"""
Test Document Processor

Transcribes the 36 test documents (20 invoices, 11 receipts, 5 POs) from the
4 pages in test-documents/extracted/ and runs them through the logistics
pipeline. Simulates what the WorkBuddy agent would extract from the images.

Each document is cropped to test-documents/<type>/pPP_NN.png (page PP,
position NN in reading order) — that path is the record's source_ref.

Everything is recorded AS PRINTED. Where the document itself is contradictory
or unreadable, the record gets a flag and a `notes` line describing what is on
the page — Logistics never decides which figure is right:
- conflicting_values: two different totals / SST figures printed (016, 033, A04, A05, A06)
- handwritten: INV-2026-029
- unreadable_field: garbled unit prices (028, 024)
- blurry_image: INV-2026-012 (tel/SSM), INV-2026-036 (low-res scan)
- no_po_reference: INV-2026-028 ("TIADA / NOT PROVIDED")
INV-2026-020 appears twice (p02_07 and p03_11) — Financial catches the duplicate.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.pipeline import LogisticsPipeline

SCHEMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schemas")

# Default confidence for clearly printed fields; per-document overrides below.
INVOICE_CONF = {"vendor_name": 0.95, "invoice_number": 0.95, "invoice_date": 0.95, "po_reference": 0.95, "line_items": 0.92, "grand_total": 0.95, "total_tax": 0.95}
RECEIPT_CONF = {"vendor_name": 0.95, "receipt_date": 0.95, "amount": 0.95}
ORDER_CONF = {"po_number": 0.95, "po_date": 0.95, "vendor_name": 0.95, "line_items": 0.92, "grand_total": 0.95}


def _finish(rec, source_ref, conf, flags, notes):
    rec.update({
        "currency": "MYR",
        "source_ref": f"test-documents/{source_ref}.png",
        "confidence": conf,
        "status": "flagged" if flags else "clean",
        "flags": list(flags),
    })
    if notes:
        rec["notes"] = notes
    return rec


def _qty_lines(lines):
    # SST is only printed per document on this set, so per-line tax is unknown (None), not 0.
    return [{"description": d, "quantity": q, "unit_price": p, "tax_amount": None, "tax_rate": None} for d, q, p in lines]


def invoice(src, number, vendor, date, po_ref, lines, subtotal, total_tax, grand_total, flags=(), notes=None, conf=None):
    return _finish({
        "document_type": "invoice",
        "vendor_name": vendor,
        "invoice_number": number,
        "invoice_date": date,
        "due_date": None,  # no due date is printed on any invoice in this set
        "po_reference": po_ref,
        "line_items": _qty_lines(lines),
        "subtotal": subtotal,
        "total_tax": total_tax,
        "tax_rate": 10,  # every document in this set prints "SST 10%"
        "grand_total": grand_total,
    }, f"invoices/{src}", {**INVOICE_CONF, **(conf or {})}, flags, notes)


def receipt(src, number, vendor, date, lines, subtotal, tax, amount, flags=(), notes=None, conf=None):
    return _finish({
        "document_type": "receipt",
        "vendor_name": vendor,
        "receipt_number": number,
        "receipt_date": date,
        "payment_method": None,  # not printed
        "line_items": [{"description": d, "amount": a} for d, a in lines],
        "subtotal": subtotal,
        "tax_amount": tax,
        "tax_rate": 10,
        "amount": amount,
        "invoice_reference": None,
    }, f"receipts/{src}", {**RECEIPT_CONF, **(conf or {})}, flags, notes)


def order(src, number, buyer, date, vendor, delivery, lines, subtotal, total_tax, grand_total, flags=(), notes=None, conf=None):
    return _finish({
        "document_type": "order",
        "po_number": number,
        "po_date": date,
        "vendor_name": vendor,
        "buyer_name": buyer,
        "delivery_date": delivery,
        "line_items": _qty_lines(lines),
        "subtotal": subtotal,
        "total_tax": total_tax,
        "tax_rate": 10,
        "grand_total": grand_total,
    }, f"orders/{src}", {**ORDER_CONF, **(conf or {})}, flags, notes)


INV_020 = ("INV-2026-020", "Mesin Teknik Malaysia Sdn Bhd", "2026-10-11", "PO-MT-3535",
           [("Minyak pelincir / Lubricant oil", 40, 22.00), ("Berus logam / Metal brush", 20, 6.50)],
           1010.00, 101.00, 1111.00)

DOCUMENTS = [
    # ── Page 1 ──
    invoice("p01_01", "INV-2026-016", "Puteri Kraf Sdn Bhd", "2026-10-07", "PO-PK-9900",
            [("Beg canvas / Canvas bag", 30, 10.00), ("Stiker label / Label sticker", 20, 5.00)],
            400.00, 40.00, 425.00, flags=["conflicting_values"], conf={"grand_total": 0.5},
            notes="Two totals printed: 'TOTAL AMOUNT: RM 425.00' and a large 'RM45.70' below it. grand_total records the labelled TOTAL AMOUNT."),
    invoice("p01_02", "INV-2026-029", "Warisan Supply", "2026-10-20", "PO-WS-1010",
            [("Rantai besi / Iron chain", 15, 32.00), ("Pengapit logam / Metal clamp", 25, 5.00)],
            605.00, 60.50, 665.50, flags=["handwritten"],
            conf={"vendor_name": 0.75, "invoice_number": 0.8, "invoice_date": 0.75, "po_reference": 0.7},
            notes="Invoice number, vendor, address, date and PO ref are handwritten. Tel unreadable, SSM blank."),
    invoice("p01_03", "INV-2026-028", "Seri Murni Pembekal Sdn Bhd", "2026-10-19", None,
            [("Tuala kain / Fabric towel", 50, 12.00), ("Sabun pencuci / Washing soap", 30, 9.00)],
            870.00, 87.00, 957.00, flags=["no_po_reference", "unreadable_field"], conf={"line_items": 0.6},
            notes="PO Ref printed as '[TIADA / NOT PROVIDED]'. Unit price of 'Tuala kain' printed as '12.0ai' (last character unreadable); recorded 12.00, amount column shows 600.00."),

    # ── Page 2 ──
    receipt("p02_01", "REC-009", "Kedai Runcit Aman", "2026-10-02",
            [("Air mineral / Mineral water (24 botol)", 32.00), ("Tisu / Tissue box", 15.00)],
            47.00, 4.70, 51.70),
    invoice("p02_02", "INV-2026-018", "Delta Office Supplies Sdn Bhd", "2026-10-09", "PO-DO-1313",
            [("Binder file / Fail folder", 40, 8.50), ("Marker pen / Pen marker", 60, 3.20)],
            532.00, 53.20, 585.20, notes="A second, blank 'PO Ref:' line is printed below PO-DO-1313."),
    invoice("p02_03", "INV-2026-012", "Sri Jaya Trading Sdn Bhd", "2026-10-03", "PO-SJ-1122",
            [("Kertas A4 / A4 paper", 20, 12.00), ("Pen ballpoint / Pen", 100, 0.80)],
            320.00, 32.00, 352.00, flags=["blurry_image"], conf={"vendor_name": 0.85},
            notes="Tel and SSM are blurred. 'Kertas A4 / A4 paper' is double-printed on one line."),
    order("p02_04", "PO-2026-A05", "Bahagian Keselamatan", "2026-10-16", "Peralatan Keselamatan Sdn Bhd", "2026-11-08",
          [("Topi keselamatan / Safety helmet", 20, 45.00), ("Kasut keselamatan / Safety shoe", 15, 80.00)],
          2100.00, 21.00, 2310.00, flags=["conflicting_values"], conf={"grand_total": 0.5},
          notes="Two totals printed: 'Grand Total: RM2310.00' and a large 'RM2100.00' below it. grand_total records the labelled Grand Total."),
    receipt("p02_05", "REC-012", "Kafe Mesra", "2026-10-05",
            [("Makan tengahari / Lunch set", 96.00), ("Air teh / Teh tarik", 12.00)],
            108.00, 10.80, 118.80),
    invoice("p02_06", "INV-2026-014", "Tekun Logistik Sdn Bhd", "2026-10-05", "PO-TL-5566",
            [("Kotak kadbod / Cardboard box", 100, 1.80), ("Tape packing / Packing tape", 50, 4.50)],
            405.00, 40.50, 445.50),
    invoice("p02_07", *INV_020),
    invoice("p02_08", "INV-2026-021", "Fast Courier Sdn Bhd", "2026-10-12", "PO-FC-4646",
            [("Perkhidmatan penghantaran / Delivery service", 35, 18.00), ("Bungkus khas / Special packaging", 35, 3.00)],
            735.00, 73.50, 808.50),
    invoice("p02_09", "INV-2026-022", "Cat Warna Sdn Bhd", "2026-10-13", "PO-CW-5757",
            [("Cat dinding / Wall paint", 15, 78.00), ("Berus cat / Paint brush", 25, 9.00)],
            1395.00, 139.50, 1534.50),
    invoice("p02_10", "INV-2026-023", "Sistem Komputer MY Sdn Bhd", "2026-10-14", "PO-SK-6868",
            [("Kabel LAN / LAN cable", 30, 16.00), ("Port USB / USB hub", 15, 24.00)],
            840.00, 84.00, 924.00),
    invoice("p02_11", "INV-2026-024", "Rumah Kaca Sdn Bhd", "2026-10-15", "PO-RK-7979",
            [("Cermin tingkap / Window glass", 8, 120.00), ("Pelekat cermin / Glass sealant", 12, 18.00)],
            1176.00, 117.60, 1293.60, flags=["unreadable_field"], conf={"line_items": 0.65},
            notes="Unit prices printed as '120ping' and '18.tiub' (unit text run into the price); recorded 120.00 and 18.00."),
    invoice("p02_12", "INV-2026-026", "Taman Hijau Landskap Sdn Bhd", "2026-10-17", "PO-TH-9191",
            [("Baja tumbuhan / Plant fertilizer", 30, 28.00), ("Gunting dahan / Branch cutter", 10, 35.00)],
            1190.00, 119.00, 1309.00),

    # ── Page 3 ──
    invoice("p03_01", "INV-2026-013", "Central Supply MY Sdn Bhd", "2026-10-04", "PO-CS-3344",
            [("Sarung tangan getah / Rubber glove 30 box", 30, 15.00), ("Pembersih lantai / Floor cleaner", 15, 8.00)],
            570.00, 57.00, 627.00),
    invoice("p03_02", "INV-2026-011", "Maju Teknik Sdn Bhd", "2026-10-02", "PO-MT-0987",
            [("Bekas plastik / Plastic container", 50, 2.50), ("Skru besi / Iron screw", 200, 0.30)],
            185.00, 18.50, 203.50),
    receipt("p03_03", "REC-011", "Print Express", "2026-10-04",
            [("Cetakan brosur / Brochure print 500 pcs", 220.00), ("Laminating / Laminasi", 30.00)],
            250.00, 25.00, 275.00),
    receipt("p03_04", "REC-013", "Kedai Kabel & Wayar", "2026-10-06",
            [("Wayar elektrik / Electrical wire 10m", 42.00), ("Penutup soket / Socket cover", 16.00)],
            58.00, 5.80, 63.80),
    receipt("p03_05", "REC-015", "Kedai Hadiah & Pembalut", "2026-10-08",
            [("Kertas pembalut / Wrapping paper", 25.00), ("Riben hiasan / Decor ribbon", 18.00)],
            43.00, 4.30, 47.30),
    receipt("p03_06", "REC-016", "Kedai Tayar & Pam", "2026-10-09",
            [("Pam tayar / Tyre pump", 75.00), ("Pembaikan injap / Valve repair", 22.00)],
            97.00, 9.70, 106.70),
    receipt("p03_07", "REC-017", "Kedai Buku & Alat Tulis", "2026-10-10",
            [("Buku nota / Notebook", 36.00), ("Pemadam / Eraser pack", 12.00)],
            48.00, 4.80, 52.80),
    receipt("p03_08", "REC-018", "Kedai Minyak & Gas", "2026-10-11",
            [("Minyak enjin / Engine oil 4L", 120.00), ("Penapis minyak / Oil filter", 45.00)],
            165.00, 16.50, 181.50),
    order("p03_09", "PO-2026-A03", "Bahagian Kejuruteraan", "2026-10-06", "Lumi Elektrik Sdn Bhd", "2026-10-25",
          [("Mentol LED / LED bulb", 80, 6.20), ("Suis lampu / Light switch", 40, 9.00)],
          856.00, 85.60, 941.60),
    order("p03_10", "PO-2026-A04", "Bahagian Landskap", "2026-10-12", "Taman Hijau Landskap Sdn Bhd", "2026-11-02",
          [("Baja tumbuhan / Plant fertilizer", 30, 28.00), ("Cunting dahan / Branch cutter", 10, 35.00)],
          1190.00, 119.00, 1309.00, flags=["conflicting_values"], conf={"grand_total": 0.5},
          notes="Two totals printed: 'Grand Total: RM1309.00' and a large 'RM1390.00' below it. grand_total records the labelled Grand Total."),
    invoice("p03_11", *INV_020),
    invoice("p03_12", "INV-2026-032", "Tekno Supply Sdn Bhd", "2026-10-23", "PO-TS-1301",
            [("Kabel USB / USB cable", 20, 3.00), ("Penanda / Marker pen", 15, 2.00)],
            90.00, 9.00, 99.00,
            notes="'Subtotal:' label has no value beside it; 90.00 is printed above it in the amount column."),
    invoice("p03_13", "INV-2026-033", "Buku Nusa Enterprise", "2026-10-23", "PO-BN-1302",
            [("Buku nota / Notebook", 10, 8.00), ("Pemadam / Eraser", 30, 0.50)],
            95.00, 9.50, 104.50, flags=["conflicting_values"], conf={"total_tax": 0.5},
            notes="SST printed twice: 'SST 10%: 9.50' and 9.00 in the amount column. total_tax records the labelled 9.50."),
    invoice("p03_14", "INV-2026-034", "Bersih Gadget Sdn Bhd", "2026-10-24", "PO-BG-1303",
            [("Cecair pembersih / Cleaning liquid", 6, 12.00), ("Kain lap / Cloth wipe", 12, 4.00)],
            120.00, 12.00, 132.00),

    # ── Page 4 ──
    receipt("p04_01", "REC-031", "Kedai Makan Mesra", "2026-10-24",
            [("Air Oren / Orange juice", 8.00), ("Roti canai / Flatbread", 12.00)],
            20.00, 2.00, 22.00),
    receipt("p04_02", "REC-032", "Kedai Alat Tulis Cepat", "2026-10-24",
            [("Gunting / Scissors", 14.00), ("Kertas A4 / A4 Paper", 36.00)],
            50.00, 5.00, 55.00),
    order("p04_03", "PO-2026-A06", "Bahagian Pentadbiran", "2026-10-25", "Tekno Supply Sdn Bhd", "2026-11-25",
          [("Kabel USB / USB cable", 50, 3.00), ("Penanda / Marker pen", 40, 2.00)],
          230.00, 23.00, 253.00, flags=["conflicting_values"],
          notes="An unlabelled '49.00' is printed under the subtotal."),
    order("p04_04", "PO-2026-A07", "Bahapian Operasi", "2026-10-25", "Buku Nusa Enterprise", "2026-11-28",
          [("Buku nota / Notebook", 30, 8.00), ("Pemadam / Eraser", 80, 0.50)],
          280.00, 28.00, 308.00),
    invoice("p04_05", "INV-2026-035", "Logam Maju Sdn Bhd", "2026-10-25", "PO-LM-1304",
            [("Skru / Screw pack", 25, 6.00), ("Nat / Nut pack", 20, 5.00)],
            250.00, 25.00, 275.00),
    receipt("p04_06", "REC-033", "Kedai Hardware Murah", "2026-10-26",
            [("Paku / Nail box", 24.00), ("Tali plastik / Plastic rope", 16.00)],
            40.00, 4.00, 44.00),
    invoice("p04_07", "INV-2026-036", "Lampu Terang Sdn Bhd", "2026-10-26", "PO-LT-1305",
            [("Mentol LED / LED bulb", 12, 15.00), ("Mentol LED / LED bulb", None, 0.00), ("Suis lampu / Light switch", 8, 10.00)],
            260.00, 26.00, 286.00, flags=["blurry_image"],
            conf={"vendor_name": 0.8, "invoice_number": 0.8, "invoice_date": 0.8, "po_reference": 0.75, "line_items": 0.6},
            notes="Low-resolution scan. 'Mentol LED / LED bulb' is printed twice; the second line has no quantity, unit price '.00' and amount 0.00."),
]


def main():
    print("\n" + "=" * 70)
    print(f"PROCESSING {len(DOCUMENTS)} TEST DOCUMENTS")
    print("=" * 70)

    pipeline = LogisticsPipeline(SCHEMA_DIR)

    # Build batch input
    batch_input = [
        {
            "content": f"Document: {d.get('invoice_number') or d.get('receipt_number') or d.get('po_number')}",
            "source_ref": d["source_ref"],
            "extracted": d,
            "filename": d["source_ref"],
        }
        for d in DOCUMENTS
    ]

    # Process
    records = pipeline.process_batch(batch_input)
    summary = pipeline.get_summary(records)

    # Print summary
    print(f"\n--- SUMMARY ---")
    print(f"  Total documents: {summary['total_documents']}")
    print(f"  By status:")
    for status, count in summary['by_status'].items():
        print(f"    {status}: {count}")
    print(f"  By type:")
    for doc_type, count in summary['by_type'].items():
        print(f"    {doc_type}: {count}")
    print(f"  Total flags: {summary['total_flags']}")
    print(f"  Unique flags: {', '.join(summary['unique_flags'])}")
    print(f"  Escalations: {summary['escalations_count']}")

    # Print escalations
    if summary['escalations']:
        print(f"\n--- ESCALATIONS (need owner verification) ---")
        for esc in summary['escalations']:
            print(f"  - {esc}")

    # Print flagged records
    print(f"\n--- FLAGGED RECORDS ---")
    for r in records:
        if r.get("status") == "flagged":
            doc_id = r.get("invoice_number") or r.get("receipt_number") or r.get("po_number")
            flags = r.get("flags", [])
            print(f"  [{r['document_type'].upper()}] {doc_id} — {r.get('vendor_name', '?')}: {flags}")

    # Print error records
    print(f"\n--- ERROR RECORDS ---")
    for r in records:
        if r.get("status") == "error":
            print(f"  {r.get('source_ref', '?')}: {r.get('flags', [])}")

    # Write output
    output_path = os.path.join(os.path.dirname(__file__), "output.json")
    output_json = pipeline.format_output(records)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output_json)
    print(f"\n--- OUTPUT ---")
    print(f"  Written to: {output_path}")
    print(f"  Records: {len(records)}")


if __name__ == "__main__":
    main()
