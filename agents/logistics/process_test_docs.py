"""
Test Document Processor

Transcribes the 35 test documents from the PDF and runs them
through the logistics pipeline. Simulates what the WorkBuddy
agent would extract from the images.

The documents include deliberately bad ones:
- SST 10% (invalid in Malaysia — valid rates: 0%, 6%, 8%)
- Wrong totals (e.g., Subtotal 400 + SST 40 = 440, but printed Total = 45.70)
- Missing PO references (TIADA / NOT PROVIDED)
- Blurry/hard to read text
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.pipeline import LogisticsPipeline

SCHEMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schemas")

# Define all 35 documents (transcribed from the PDF images)
# Each record follows the schema, with confidence scores and flags

DOCUMENTS = [
    # ============ INVOICES ============
    # INV-2026-040: WRONG TOTAL (400 + 40 = 440, but printed 45.70) + SST 10% (invalid)
    {
        "document_type": "invoice",
        "vendor_name": "Pulau Ketel Sdn Bhd",
        "vendor_sst_id": "W10-2001-220004",
        "invoice_number": "INV-2026-040",
        "invoice_date": "2026-10-02",
        "po_reference": "PO-PA-26-0002",
        "line_items": [
            {"description": "Big canvas / Canvas bag", "quantity": 30, "unit_price": 10.00, "tax_amount": 0.00, "tax_rate": None},
            {"description": "Stiker label / Label sticker", "quantity": 5, "unit_price": 5.00, "tax_amount": 0.00, "tax_rate": None},
        ],
        "subtotal": 400.00,
        "total_tax": 40.00,  # 10% — INVALID (should be 0/6/8%)
        "grand_total": 45.70,  # WRONG — should be 440.00
        "currency": "MYR",
        "source_ref": "invoice_001.png",
        "confidence": {"vendor_name": 0.95, "invoice_number": 0.95, "invoice_date": 0.90, "po_reference": 0.90, "line_items": 0.90, "grand_total": 0.95, "total_tax": 0.90},
        "status": "flagged",
        "flags": ["wrong_total", "invalid_sst_rate"],
    },
    # INV-2026-029: Normal invoice
    {
        "document_type": "invoice",
        "vendor_name": "Minuma Supply",
        "vendor_sst_id": "J11-1332-220009-0",
        "invoice_number": "INV-2026-029",
        "invoice_date": "2026-10-05",
        "po_reference": "PO-MG-1010",
        "line_items": [
            {"description": "Kertas A4 / A4 paper", "quantity": 10, "unit_price": 22.00, "tax_amount": 13.20, "tax_rate": 6},
            {"description": "Pen hitam / Black pen", "quantity": 20, "unit_price": 4.50, "tax_amount": 5.40, "tax_rate": 6},
            {"description": "Metal clamp", "quantity": 25, "unit_price": 2.00, "tax_amount": 3.00, "tax_rate": 6},
        ],
        "subtotal": 405.00,
        "total_tax": 21.60,
        "grand_total": 665.50,
        "currency": "MYR",
        "source_ref": "invoice_002.png",
        "confidence": {"vendor_name": 0.95, "invoice_number": 0.95, "invoice_date": 0.90, "po_reference": 0.90, "line_items": 0.92, "grand_total": 0.95, "total_tax": 0.92},
        "status": "clean",
        "flags": [],
    },
    # INV-2026-026: NO PO REFERENCE + SST 10% (invalid)
    {
        "document_type": "invoice",
        "vendor_name": "Syarikat Makmal Sdn Bhd",
        "vendor_sst_id": "W10-0890-220011-0",
        "invoice_number": "INV-2026-026",
        "invoice_date": "2026-10-07",
        "po_reference": None,  # MISSING — TIADA / NOT PROVIDED
        "line_items": [
            {"description": "Tudung kismis / Raisin bread", "quantity": 10, "unit_price": 7.50, "tax_amount": 6.00, "tax_rate": 8},
            {"description": "Sabun pencuci / Washing soap", "quantity": 10, "unit_price": 9.00, "tax_amount": 0.00, "tax_rate": 0},
        ],
        "subtotal": 675.00,
        "total_tax": 7.00,
        "grand_total": 957.00,
        "currency": "MYR",
        "source_ref": "invoice_003.png",
        "confidence": {"vendor_name": 0.95, "invoice_number": 0.95, "invoice_date": 0.90, "po_reference": 0.0, "line_items": 0.90, "grand_total": 0.95, "total_tax": 0.85},
        "status": "flagged",
        "flags": ["no_po_reference"],
    },
    # INV-2026-018
    {
        "document_type": "invoice",
        "vendor_name": "Minuma Office Supplies Sdn Bhd",
        "vendor_sst_id": "J11-1332-220009-0",
        "invoice_number": "INV-2026-018",
        "invoice_date": "2026-09-12",
        "po_reference": "PO-SJ-1010",
        "line_items": [
            {"description": "Binder clip", "quantity": 30, "unit_price": 3.30, "tax_amount": 5.94, "tax_rate": 6},
            {"description": "Stapler heavy duty", "quantity": 1, "unit_price": 1.00, "tax_amount": 0.06, "tax_rate": 6},
        ],
        "subtotal": 522.00,
        "total_tax": 3.00,
        "grand_total": 585.20,
        "currency": "MYR",
        "source_ref": "invoice_004.png",
        "confidence": {"vendor_name": 0.95, "invoice_number": 0.95, "invoice_date": 0.90, "po_reference": 0.90, "line_items": 0.90, "grand_total": 0.95, "total_tax": 0.90},
        "status": "clean",
        "flags": [],
    },
    # INV-2026-012
    {
        "document_type": "invoice",
        "vendor_name": "Sri Jaya Trading Sdn Bhd",
        "vendor_sst_id": "W10-2001-220005-0",
        "invoice_number": "INV-2026-012",
        "invoice_date": "2026-09-14",
        "po_reference": "PO-SJ-1122",
        "line_items": [
            {"description": "Gunting / Scissors", "quantity": 1, "unit_price": 0.80, "tax_amount": 0.05, "tax_rate": 6},
            {"description": "Pen ballpoint / Ballpoint pen", "quantity": 10, "unit_price": 0.50, "tax_amount": 0.30, "tax_rate": 6},
        ],
        "subtotal": 52.00,
        "total_tax": 1.00,
        "grand_total": 80.00,
        "currency": "MYR",
        "source_ref": "invoice_005.png",
        "confidence": {"vendor_name": 0.95, "invoice_number": 0.95, "invoice_date": 0.90, "po_reference": 0.90, "line_items": 0.90, "grand_total": 0.95, "total_tax": 0.90},
        "status": "clean",
        "flags": [],
    },
    # INV-2026-014
    {
        "document_type": "invoice",
        "vendor_name": "Tulus Logistik Sdn Bhd",
        "vendor_sst_id": "W10-2001-220006-0",
        "invoice_number": "INV-2026-014",
        "invoice_date": "2026-09-12",
        "po_reference": "PO-TL-1009",
        "line_items": [
            {"description": "Kotak kadbod / Cardboard box", "quantity": 10, "unit_price": 1.80, "tax_amount": 1.08, "tax_rate": 6},
            {"description": "Stretch wrap film", "quantity": 10, "unit_price": 3.10, "tax_amount": 1.86, "tax_rate": 6},
        ],
        "subtotal": 400.00,
        "total_tax": 3.00,
        "grand_total": 445.50,
        "currency": "MYR",
        "source_ref": "invoice_006.png",
        "confidence": {"vendor_name": 0.95, "invoice_number": 0.95, "invoice_date": 0.90, "po_reference": 0.90, "line_items": 0.90, "grand_total": 0.95, "total_tax": 0.90},
        "status": "clean",
        "flags": [],
    },
    # INV-2026-025
    {
        "document_type": "invoice",
        "vendor_name": "Kedai Tanda Maju Mulia Sdn Bhd",
        "vendor_sst_id": "C10-7732-220010-0",
        "invoice_number": "INV-2026-025",
        "invoice_date": "2026-09-15",
        "po_reference": None,  # No PO visible
        "line_items": [
            {"description": "Whiteboard", "quantity": 10, "unit_price": 4.00, "tax_amount": 2.40, "tax_rate": 6},
            {"description": "Buku log / Log book", "quantity": 5, "unit_price": 2.00, "tax_amount": 0.60, "tax_rate": 6},
            {"description": "Borang permohonan / Form", "quantity": 10, "unit_price": 0.50, "tax_amount": 0.30, "tax_rate": 6},
        ],
        "subtotal": 1080.00,
        "total_tax": 1.00,
        "grand_total": 1111.00,
        "currency": "MYR",
        "source_ref": "invoice_007.png",
        "confidence": {"vendor_name": 0.92, "invoice_number": 0.95, "invoice_date": 0.90, "po_reference": 0.0, "line_items": 0.88, "grand_total": 0.95, "total_tax": 0.85},
        "status": "flagged",
        "flags": ["no_po_reference"],
    },
    # INV-2026-019
    {
        "document_type": "invoice",
        "vendor_name": "Fast Courier Sdn Bhd",
        "invoice_number": "INV-2026-019",
        "invoice_date": "2026-09-20",
        "po_reference": "PO-FC-4040",
        "line_items": [
            {"description": "Penghantaran dokumen / Document delivery", "quantity": 10, "unit_price": 10.00, "tax_amount": 6.00, "tax_rate": 6},
            {"description": "Penghantaran pakej / Package delivery", "quantity": 5, "unit_price": 8.00, "tax_amount": 2.40, "tax_rate": 6},
        ],
        "subtotal": 720.00,
        "total_tax": 18.00,
        "grand_total": 808.50,
        "currency": "MYR",
        "source_ref": "invoice_008.png",
        "confidence": {"vendor_name": 0.95, "invoice_number": 0.95, "invoice_date": 0.90, "po_reference": 0.90, "line_items": 0.90, "grand_total": 0.95, "total_tax": 0.90},
        "status": "clean",
        "flags": [],
    },
    # INV-2026-022: NO PO, amount > RM 500
    {
        "document_type": "invoice",
        "vendor_name": "Car Wipers Sdn Bhd",
        "vendor_sst_id": "C10-7732-220012-0",
        "invoice_number": "INV-2026-022",
        "invoice_date": "2026-10-03",
        "po_reference": None,  # TIADA / NOT PROVIDED
        "line_items": [
            {"description": "Car wipers / Wiper blades", "quantity": 10, "unit_price": 75.00, "tax_amount": 45.00, "tax_rate": 6},
            {"description": "Busa calit / Foam sponge", "quantity": 20, "unit_price": 9.00, "tax_amount": 10.80, "tax_rate": 6},
        ],
        "subtotal": 1395.00,
        "total_tax": 15.00,
        "grand_total": 1534.50,
        "currency": "MYR",
        "source_ref": "invoice_009.png",
        "confidence": {"vendor_name": 0.95, "invoice_number": 0.95, "invoice_date": 0.90, "po_reference": 0.0, "line_items": 0.90, "grand_total": 0.95, "total_tax": 0.90},
        "status": "flagged",
        "flags": ["no_po_reference"],
    },
    # INV-2026-023
    {
        "document_type": "invoice",
        "vendor_name": "Sistem Komputer MT Sdn Bhd",
        "vendor_sst_id": "P10-2001-220015-0",
        "invoice_number": "INV-2026-023",
        "invoice_date": "2026-09-14",
        "po_reference": "PO-SK-0303",
        "line_items": [
            {"description": "Kabel LAN / LAN cable", "quantity": 1, "unit_price": 15.00, "tax_amount": 0.90, "tax_rate": 6},
            {"description": "Pintu USB / USB hub", "quantity": 2, "unit_price": 360.00, "tax_amount": 43.20, "tax_rate": 6},
        ],
        "subtotal": 840.00,
        "total_tax": 10.00,
        "grand_total": 924.00,
        "currency": "MYR",
        "source_ref": "invoice_010.png",
        "confidence": {"vendor_name": 0.95, "invoice_number": 0.95, "invoice_date": 0.90, "po_reference": 0.90, "line_items": 0.90, "grand_total": 0.95, "total_tax": 0.90},
        "status": "clean",
        "flags": [],
    },
    # INV-2026-024
    {
        "document_type": "invoice",
        "vendor_name": "Rumahku Harum Sdn Bhd",
        "vendor_sst_id": "A10-2001-220016-0",
        "invoice_number": "INV-2026-024",
        "invoice_date": "2026-09-14",
        "po_reference": None,
        "line_items": [
            {"description": "Carca begkas / Luggage bag", "quantity": 3, "unit_price": 6.00, "tax_amount": 1.08, "tax_rate": 6},
            {"description": "Bantal tikar / Pillow", "quantity": 5, "unit_price": 2.00, "tax_amount": 0.60, "tax_rate": 6},
            {"description": "Penyapu / Broom", "quantity": 5, "unit_price": 2.00, "tax_amount": 0.60, "tax_rate": 6},
        ],
        "subtotal": 1178.00,
        "total_tax": 7.00,
        "grand_total": 1293.00,
        "currency": "MYR",
        "source_ref": "invoice_011.png",
        "confidence": {"vendor_name": 0.95, "invoice_number": 0.95, "invoice_date": 0.90, "po_reference": 0.0, "line_items": 0.88, "grand_total": 0.95, "total_tax": 0.90},
        "status": "flagged",
        "flags": ["no_po_reference"],
    },
    # INV-2026-028
    {
        "document_type": "invoice",
        "vendor_name": "Taman Hijau Landskap Sdn Bhd",
        "vendor_sst_id": "B10-6543-220017-0",
        "invoice_number": "INV-2026-028",
        "invoice_date": "2026-09-17",
        "po_reference": "PO-TH-7878",
        "line_items": [
            {"description": "Baja organik / Organic fertilizer", "quantity": 10, "unit_price": 10.00, "tax_amount": 6.00, "tax_rate": 6},
            {"description": "Pokok herba / Herb plant", "quantity": 10, "unit_price": 5.00, "tax_amount": 3.00, "tax_rate": 6},
            {"description": "Benih taman / Garden seeds", "quantity": 10, "unit_price": 10.00, "tax_amount": 6.00, "tax_rate": 6},
        ],
        "subtotal": 1116.00,
        "total_tax": 3.00,
        "grand_total": 1209.00,
        "currency": "MYR",
        "source_ref": "invoice_012.png",
        "confidence": {"vendor_name": 0.95, "invoice_number": 0.95, "invoice_date": 0.90, "po_reference": 0.90, "line_items": 0.90, "grand_total": 0.95, "total_tax": 0.90},
        "status": "clean",
        "flags": [],
    },
    # INV-2026-013
    {
        "document_type": "invoice",
        "vendor_name": "Cermin Tuanku MY Sdn Bhd",
        "vendor_sst_id": "C10-7732-220018-0",
        "invoice_number": "INV-2026-013",
        "invoice_date": "2026-09-19",
        "po_reference": None,
        "line_items": [
            {"description": "Cermin besar / Large mirror", "quantity": 1, "unit_price": 10.00, "tax_amount": 0.60, "tax_rate": 6},
            {"description": "Pengilat cermin / Mirror polish", "quantity": 1, "unit_price": 0.20, "tax_amount": 0.01, "tax_rate": 6},
            {"description": "Perekat cermin / Mirror adhesive", "quantity": 1, "unit_price": 0.50, "tax_amount": 0.03, "tax_rate": 6},
        ],
        "subtotal": 570.00,
        "total_tax": 57.00,
        "grand_total": 627.00,
        "currency": "MYR",
        "source_ref": "invoice_013.png",
        "confidence": {"vendor_name": 0.92, "invoice_number": 0.95, "invoice_date": 0.88, "po_reference": 0.0, "line_items": 0.85, "grand_total": 0.92, "total_tax": 0.85},
        "status": "flagged",
        "flags": ["no_po_reference"],
    },
    # INV-2026-011
    {
        "document_type": "invoice",
        "vendor_name": "Maja Snack Sdn Bhd",
        "vendor_sst_id": "C10-1234-220019-0",
        "invoice_number": "INV-2026-011",
        "invoice_date": "2026-09-22",
        "po_reference": "PO-MS-9999",
        "line_items": [
            {"description": "Maggi kari / Maggi curry", "quantity": 10, "unit_price": 1.00, "tax_amount": 0.60, "tax_rate": 6},
            {"description": "Teh tarik / Milk tea", "quantity": 10, "unit_price": 1.00, "tax_amount": 0.60, "tax_rate": 6},
        ],
        "subtotal": 192.00,
        "total_tax": 11.50,
        "grand_total": 203.50,
        "currency": "MYR",
        "source_ref": "invoice_014.png",
        "confidence": {"vendor_name": 0.95, "invoice_number": 0.95, "invoice_date": 0.90, "po_reference": 0.90, "line_items": 0.90, "grand_total": 0.95, "total_tax": 0.90},
        "status": "clean",
        "flags": [],
    },
    # INV-2026-003
    {
        "document_type": "invoice",
        "vendor_name": "Kasut Tentera Malaysia Sdn Bhd",
        "vendor_sst_id": "C10-7732-220020-0",
        "invoice_number": "INV-2026-003",
        "invoice_date": "2026-09-08",
        "po_reference": None,
        "line_items": [
            {"description": "Minyak griser / Grease oil", "quantity": 3, "unit_price": 5.00, "tax_amount": 0.90, "tax_rate": 6},
            {"description": "Alat ujian / Test equipment", "quantity": 3, "unit_price": 2.00, "tax_amount": 0.36, "tax_rate": 6},
        ],
        "subtotal": 108.00,
        "total_tax": 3.00,
        "grand_total": 111.00,
        "currency": "MYR",
        "source_ref": "invoice_015.png",
        "confidence": {"vendor_name": 0.95, "invoice_number": 0.95, "invoice_date": 0.90, "po_reference": 0.0, "line_items": 0.90, "grand_total": 0.95, "total_tax": 0.90},
        "status": "flagged",
        "flags": ["no_po_reference"],
    },
    # INV-2026-030
    {
        "document_type": "invoice",
        "vendor_name": "Baka Busa Enterprise",
        "vendor_sst_id": "P10-2001-220021-0",
        "invoice_number": "INV-2026-030",
        "invoice_date": "2026-10-06",
        "po_reference": "PO-BB-1302",
        "line_items": [
            {"description": "Buku nota / Notebook", "quantity": 10, "unit_price": 4.00, "tax_amount": 2.40, "tax_rate": 6},
            {"description": "Penanda / Marker pen", "quantity": 10, "unit_price": 3.50, "tax_amount": 2.10, "tax_rate": 6},
        ],
        "subtotal": 100.00,
        "total_tax": 4.50,
        "grand_total": 104.50,
        "currency": "MYR",
        "source_ref": "invoice_016.png",
        "confidence": {"vendor_name": 0.95, "invoice_number": 0.95, "invoice_date": 0.90, "po_reference": 0.90, "line_items": 0.90, "grand_total": 0.95, "total_tax": 0.90},
        "status": "clean",
        "flags": [],
    },
    # INV-2026-034
    {
        "document_type": "invoice",
        "vendor_name": "Berris Gadget Sdn Bhd",
        "vendor_sst_id": "C10-7732-220022-0",
        "invoice_number": "INV-2026-034",
        "invoice_date": "2026-10-06",
        "po_reference": "PO-BG-1234",
        "line_items": [
            {"description": "Cecair pembersih / Cleaning liquid", "quantity": 4, "unit_price": 12.00, "tax_amount": 2.88, "tax_rate": 6},
            {"description": "Kain lap / Cleaning cloth", "quantity": 1, "unit_price": 0.00, "tax_amount": 0.00, "tax_rate": 6},
        ],
        "subtotal": 120.00,
        "total_tax": 12.00,
        "grand_total": 132.00,
        "currency": "MYR",
        "source_ref": "invoice_017.png",
        "confidence": {"vendor_name": 0.95, "invoice_number": 0.95, "invoice_date": 0.90, "po_reference": 0.90, "line_items": 0.90, "grand_total": 0.95, "total_tax": 0.90},
        "status": "clean",
        "flags": [],
    },
    # INV-2026-035
    {
        "document_type": "invoice",
        "vendor_name": "Logam Maju Sdn Bhd",
        "vendor_sst_id": "C10-7732-220023-0",
        "invoice_number": "INV-2026-035",
        "invoice_date": "2026-10-07",
        "po_reference": "PO-LM-1304",
        "line_items": [
            {"description": "Skru / Screw pack", "quantity": 10, "unit_price": 4.00, "tax_amount": 2.40, "tax_rate": 6},
            {"description": "Nat / Nut pack", "quantity": 10, "unit_price": 0.00, "tax_amount": 0.00, "tax_rate": 6},
        ],
        "subtotal": 250.00,
        "total_tax": 20.00,
        "grand_total": 270.00,
        "currency": "MYR",
        "source_ref": "invoice_018.png",
        "confidence": {"vendor_name": 0.95, "invoice_number": 0.95, "invoice_date": 0.90, "po_reference": 0.90, "line_items": 0.90, "grand_total": 0.95, "total_tax": 0.90},
        "status": "clean",
        "flags": [],
    },
    # INV-2026-036: BLURRY — lower confidence
    {
        "document_type": "invoice",
        "vendor_name": "Lapop Tuning Sdn Bhd",
        "vendor_sst_id": "C10-7732-220024-0",
        "invoice_number": "INV-2026-036",
        "invoice_date": "2026-10-05",
        "po_reference": "PO-LT-1305",
        "line_items": [
            {"description": "Minyak SDK / SDK oil", "quantity": 12, "unit_price": 11.00, "tax_amount": 7.92, "tax_rate": 6},
            {"description": "Minyak RBD / RBD oil", "quantity": 8, "unit_price": 0.00, "tax_amount": 0.00, "tax_rate": 6},
        ],
        "subtotal": 195.00,
        "total_tax": 11.00,
        "grand_total": 206.00,
        "currency": "MYR",
        "source_ref": "invoice_019.png",
        "confidence": {"vendor_name": 0.60, "invoice_number": 0.75, "invoice_date": 0.65, "po_reference": 0.70, "line_items": 0.60, "grand_total": 0.80, "total_tax": 0.70},
        "status": "flagged",
        "flags": ["blurry_image"],
    },

    # ============ RECEIPTS ============
    # REC-006
    {
        "document_type": "receipt",
        "vendor_name": "Kedai Runcit Aman",
        "receipt_number": "REC-006",
        "receipt_date": "2026-10-02",
        "payment_method": "cash",
        "amount": 51.70,
        "tax_amount": 4.70,
        "invoice_reference": None,
        "currency": "MYR",
        "source_ref": "receipt_001.png",
        "confidence": {"vendor_name": 0.90, "receipt_date": 0.90, "amount": 0.90, "payment_method": 0.80},
        "status": "clean",
        "flags": [],
    },
    # REC-012
    {
        "document_type": "receipt",
        "vendor_name": "Kedai Runcit",
        "vendor_sst_id": "J11-1332-220013-0",
        "receipt_number": "REC-012",
        "receipt_date": "2026-10-04",
        "payment_method": "cash",
        "amount": 110.80,
        "tax_amount": 10.80,
        "invoice_reference": None,
        "currency": "MYR",
        "source_ref": "receipt_002.png",
        "confidence": {"vendor_name": 0.90, "receipt_date": 0.90, "amount": 0.90, "payment_method": 0.80},
        "status": "clean",
        "flags": [],
    },
    # Print Express
    {
        "document_type": "receipt",
        "vendor_name": "Print Express",
        "vendor_sst_id": "C10-7732-220025-0",
        "receipt_number": "REC-017",
        "receipt_date": "2026-10-08",
        "payment_method": "duitnow",
        "amount": 270.00,
        "tax_amount": 20.00,
        "invoice_reference": None,
        "currency": "MYR",
        "source_ref": "receipt_003.png",
        "confidence": {"vendor_name": 0.88, "receipt_date": 0.88, "amount": 0.90, "payment_method": 0.80},
        "status": "clean",
        "flags": [],
    },
    # Kabel Kakit & Hujan
    {
        "document_type": "receipt",
        "vendor_name": "Kabel Kakit & Hujan",
        "receipt_number": "REC-013",
        "receipt_date": "2026-10-04",
        "payment_method": "cash",
        "amount": 553.80,
        "tax_amount": 50.30,
        "invoice_reference": None,
        "currency": "MYR",
        "source_ref": "receipt_004.png",
        "confidence": {"vendor_name": 0.88, "receipt_date": 0.88, "amount": 0.90, "payment_method": 0.80},
        "status": "clean",
        "flags": [],
    },
    # Kedai Hodong & Perabot
    {
        "document_type": "receipt",
        "vendor_name": "Kedai Hodong & Perabot",
        "receipt_number": "REC-014",
        "receipt_date": "2026-10-04",
        "payment_method": "cash",
        "amount": 47.30,
        "tax_amount": 4.30,
        "invoice_reference": None,
        "currency": "MYR",
        "source_ref": "receipt_005.png",
        "confidence": {"vendor_name": 0.88, "receipt_date": 0.88, "amount": 0.90, "payment_method": 0.80},
        "status": "clean",
        "flags": [],
    },
    # Kedai Topup & Aki
    {
        "document_type": "receipt",
        "vendor_name": "Kedai Topup & Aki",
        "receipt_number": "REC-015",
        "receipt_date": "2026-10-04",
        "payment_method": "card",
        "amount": 106.70,
        "tax_amount": 9.70,
        "invoice_reference": None,
        "currency": "MYR",
        "source_ref": "receipt_006.png",
        "confidence": {"vendor_name": 0.88, "receipt_date": 0.88, "amount": 0.90, "payment_method": 0.75},
        "status": "clean",
        "flags": [],
    },
    # Kafe Buku & Majalah
    {
        "document_type": "receipt",
        "vendor_name": "Kafe Buku & Majalah",
        "receipt_number": "REC-016",
        "receipt_date": "2026-10-04",
        "payment_method": "cash",
        "amount": 101.50,
        "tax_amount": 16.50,
        "invoice_reference": None,
        "currency": "MYR",
        "source_ref": "receipt_007.png",
        "confidence": {"vendor_name": 0.88, "receipt_date": 0.88, "amount": 0.90, "payment_method": 0.80},
        "status": "clean",
        "flags": [],
    },
    # REC-031
    {
        "document_type": "receipt",
        "vendor_name": "Kedai Makan Mesra",
        "receipt_number": "REC-031",
        "receipt_date": "2026-10-24",
        "payment_method": "cash",
        "amount": 22.00,
        "tax_amount": 2.00,
        "invoice_reference": None,
        "currency": "MYR",
        "source_ref": "receipt_008.png",
        "confidence": {"vendor_name": 0.90, "receipt_date": 0.90, "amount": 0.90, "payment_method": 0.80},
        "status": "clean",
        "flags": [],
    },
    # REC-032
    {
        "document_type": "receipt",
        "vendor_name": "Kedai Alat Tulis Cepat",
        "receipt_number": "REC-032",
        "receipt_date": "2026-10-24",
        "payment_method": "duitnow",
        "amount": 55.00,
        "tax_amount": 5.00,
        "invoice_reference": None,
        "currency": "MYR",
        "source_ref": "receipt_009.png",
        "confidence": {"vendor_name": 0.90, "receipt_date": 0.90, "amount": 0.90, "payment_method": 0.80},
        "status": "clean",
        "flags": [],
    },
    # REC-033
    {
        "document_type": "receipt",
        "vendor_name": "Kedai Hardware Murah",
        "receipt_number": "REC-033",
        "receipt_date": "2026-10-26",
        "payment_method": "cash",
        "amount": 44.00,
        "tax_amount": 4.00,
        "invoice_reference": None,
        "currency": "MYR",
        "source_ref": "receipt_010.png",
        "confidence": {"vendor_name": 0.90, "receipt_date": 0.90, "amount": 0.90, "payment_method": 0.80},
        "status": "clean",
        "flags": [],
    },

    # ============ PURCHASE ORDERS ============
    # PB-2026-003
    {
        "document_type": "order",
        "po_number": "PB-2026-003",
        "po_date": "2026-08-25",
        "vendor_name": "Tukang Kebun, Sdn. Bhd",
        "buyer_name": "Bahagian Pentadbiran Sdn Bhd",
        "delivery_date": "2026-08-26",
        "line_items": [
            {"description": "Top landscaping / Landscaping work", "quantity": 1, "unit_price": 6900.00, "tax_amount": 0.00, "tax_rate": 0},
        ],
        "subtotal": 6900.00,
        "total_tax": 450.00,
        "grand_total": 7350.00,
        "currency": "MYR",
        "source_ref": "po_001.png",
        "confidence": {"po_number": 0.95, "po_date": 0.90, "vendor_name": 0.90, "line_items": 0.88, "grand_total": 0.95},
        "status": "clean",
        "flags": [],
    },
    # PB-2026-006
    {
        "document_type": "order",
        "po_number": "PB-2026-006",
        "po_date": "2026-10-29",
        "vendor_name": "Kekalkan Operasional",
        "buyer_name": "Bahagian Pentadbiran",
        "delivery_date": "2026-10-30",
        "line_items": [
            {"description": "WiFi router", "quantity": 5, "unit_price": 30.00, "tax_amount": 9.00, "tax_rate": 6},
            {"description": "Kabel Cat6", "quantity": 20, "unit_price": 6.00, "tax_amount": 7.20, "tax_rate": 6},
            {"description": "Light switch", "quantity": 10, "unit_price": 0.50, "tax_amount": 0.30, "tax_rate": 6},
        ],
        "subtotal": 270.00,
        "total_tax": 60.00,
        "grand_total": 330.00,
        "currency": "MYR",
        "source_ref": "po_002.png",
        "confidence": {"po_number": 0.95, "po_date": 0.90, "vendor_name": 0.88, "line_items": 0.90, "grand_total": 0.95},
        "status": "clean",
        "flags": [],
    },
    # PB-2026-001
    {
        "document_type": "order",
        "po_number": "PB-2026-001",
        "po_date": "2026-10-15",
        "vendor_name": "Permata Niaga Sdn Bhd",
        "buyer_name": "Bahagian Kewangan",
        "delivery_date": "2026-10-17",
        "line_items": [
            {"description": "Wireless presenter", "quantity": 1, "unit_price": 240.00, "tax_amount": 14.40, "tax_rate": 6},
            {"description": "Smoke detector", "quantity": 1, "unit_price": 0.00, "tax_amount": 0.00, "tax_rate": 6},
        ],
        "subtotal": 240.00,
        "total_tax": 26.00,
        "grand_total": 390.00,
        "currency": "MYR",
        "source_ref": "po_003.png",
        "confidence": {"po_number": 0.95, "po_date": 0.90, "vendor_name": 0.90, "line_items": 0.90, "grand_total": 0.95},
        "status": "clean",
        "flags": [],
    },
    # PO-2026-406
    {
        "document_type": "order",
        "po_number": "PO-2026-406",
        "po_date": "2026-10-29",
        "vendor_name": "Tekno Supply Sdn Bhd",
        "buyer_name": "Bahagian Pentadbiran",
        "delivery_date": "2026-11-25",
        "line_items": [
            {"description": "Kabel USB / USB cable", "quantity": 50, "unit_price": 3.00, "tax_amount": 9.00, "tax_rate": 6},
            {"description": "Penyapu / Marker pen", "quantity": 50, "unit_price": 0.80, "tax_amount": 2.40, "tax_rate": 6},
        ],
        "subtotal": 230.00,
        "total_tax": 23.00,
        "grand_total": 253.00,
        "currency": "MYR",
        "source_ref": "po_004.png",
        "confidence": {"po_number": 0.95, "po_date": 0.90, "vendor_name": 0.88, "line_items": 0.88, "grand_total": 0.95},
        "status": "clean",
        "flags": [],
    },
    # PO-2026-407
    {
        "document_type": "order",
        "po_number": "PO-2026-407",
        "po_date": "2026-10-29",
        "vendor_name": "Buku Niaga Enterprise",
        "buyer_name": "Bahagian Operasi",
        "delivery_date": "2026-11-25",
        "line_items": [
            {"description": "Buku nota / Notebook", "quantity": 30, "unit_price": 8.00, "tax_amount": 14.40, "tax_rate": 6},
            {"description": "Petunda / Eraser", "quantity": 50, "unit_price": 0.00, "tax_amount": 0.00, "tax_rate": 6},
        ],
        "subtotal": 240.00,
        "total_tax": 28.00,
        "grand_total": 268.00,
        "currency": "MYR",
        "source_ref": "po_005.png",
        "confidence": {"po_number": 0.95, "po_date": 0.90, "vendor_name": 0.88, "line_items": 0.88, "grand_total": 0.95},
        "status": "clean",
        "flags": [],
    },
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

    # Key numbers for Financial
    print(f"\n--- KEY NUMBERS FOR FINANCIAL ---")
    total_clean = sum(r.get("grand_total") or r.get("amount") or 0
                      for r in records if r.get("status") == "clean")
    total_flagged = sum(r.get("grand_total") or r.get("amount") or 0
                        for r in records if r.get("status") == "flagged")
    print(f"  Clean total: RM {total_clean:.2f}")
    print(f"  Flagged total: RM {total_flagged:.2f}")
    print(f"  Combined: RM {total_clean + total_flagged:.2f}")


if __name__ == "__main__":
    main()
