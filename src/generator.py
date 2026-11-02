"""Generator kasus eval — schema terstruktur + reference.py + teks prompt Indonesia.

Membaca data/cases_schema.json, menghitung expected_output via reference.py
(single source of truth), merender prompt Bahasa Indonesia dengan format
ribuan titik (1.585.000), lalu menulis hasil ke data/eval_cases_generated.json.

Varian isomorfik: parameter harga digeser (shift 1.2x, 2.0x) — logika bisnis
sama, jawaban benar dihitung otomatis. Kasus dengan decision-path yang berubah
tetap valid karena expected ikut dihitung ulang.

Jalankan:
    python src/generator.py                 # tulis data/eval_cases_generated.json
    python src/generator.py --preview 5     # tampilkan N kasus pertama
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List

import reference

logger = logging.getLogger(__name__)

BASE_DIR: Path = Path(__file__).resolve().parent.parent
SCHEMA_PATH: Path = BASE_DIR / "data" / "cases_schema.json"
OUT_PATH: Path = BASE_DIR / "data" / "eval_cases_generated.json"
OUT_PATH_EN: Path = BASE_DIR / "data" / "eval_cases_en.json"

# Terjemahan nama item/kategori untuk mirror bahasa Inggris (nilai & expected
# tidak berubah — hanya teks yang dibaca manusia/juri).
EN_CATEGORY: Dict[str, str] = {
    "Elektronik": "Electronics",
    "Buku": "Books",
    "Fashion": "Fashion",
    "RT": "Household",
    "Furnitur": "Furniture",
    "Umum": "General",
    "Meja & Dapur": "Table & Kitchen",
    "Rumah Tangga": "Household",
}

EN_ITEM: Dict[str, str] = {
    "TV": "TV",
    "Buku": "Book",
    "Laptop": "Laptop",
    "Sepatu": "Shoes",
    "Paket Sabun": "Soap Pack",
    "Meja Belajar": "Study Desk",
    "Topi": "Hat",
    "Kaos": "T-Shirt",
    "Sarung Tangan": "Gloves",
    "Item A": "Item A",
    "Item B": "Item B",
    "Kursi Kayu": "Wooden Chair",
    "Cicipan": "Serving Dish",
    "Jaket": "Jacket",
    "Tas": "Bag",
    "Speaker": "Speaker",
    "Kamera": "Camera",
    "Elektronik untuk Pemula": "Electronics for Beginners",
    "Sprei": "Bedsheet",
}


def idr(value: float) -> str:
    """Format rupiah Indonesia: 1585000 -> '1.585.000', desimal pakai koma."""
    if abs(value - round(value)) < 0.005:
        return f"{int(round(value)):,}".replace(",", ".")
    return f"{value:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def idr_en(value: float) -> str:
    """English number format: 1585000 -> '1,585,000'."""
    if abs(value - round(value)) < 0.005:
        return f"{int(round(value)):,}"
    return f"{value:,.2f}"


def _category_en(name: str) -> str:
    return EN_CATEGORY.get(name, name)


def _items_text_en(items: List[Dict[str, Any]]) -> str:
    return ", ".join(
        f"{EN_ITEM.get(i['name'], i['name'])} "
        f"(category '{_category_en(i['category'])}') priced at {idr_en(float(i['price']))}"
        for i in items
    )


def pct(value: float) -> str:
    return f"{value * 100:g}%"


def _items_text(items: List[Dict[str, Any]]) -> str:
    return ", ".join(
        f"{i['name']} (kategori '{i['category']}') seharga {idr(float(i['price']))}"
        for i in items
    )


# ---------------------------------------------------------------- kalkulasi
def compute_expected(scenario: str, params: Dict[str, Any], shift: float) -> float:
    """Panggil reference.py sesuai skenario; harga digeser multiplikasi shift."""
    if scenario == "tiered_disc":
        items = params["items"]
        return reference.tiered_member_and_category(
            _scaled(items, shift),
            params["member"],
            params["member_threshold"],
            params["member_pct"],
            params["category"],
            params["category_extra_pct"],
        )
    if scenario == "exclusive":
        return reference.exclusive_best_of(
            _subtotal(params["items"], shift),
            params["member"],
            params["member_pct"],
            params["voucher"],
        )
    if scenario == "min_subtotal_voucher":
        return reference.voucher_min_subtotal(
            _scaled(params["items"], shift),
            params["shipping"],
            params["voucher"],
            params["min_subtotal"],
        )
    if scenario == "tax_after_discount":
        return reference.tax_after_discount(
            _scaled(params["items"], shift),
            params["member_pct"],
            params["tax_rate"],
        )
    if scenario == "free_shipping_after_voucher":
        return reference.free_shipping_threshold_after_voucher(
            _scaled(params["items"], shift),
            params["voucher"],
            params["shipping"],
            params["threshold"],
        )
    if scenario == "cashback_category_trap":
        return reference.cashback_category_only(
            _scaled(params["items"], shift),
            params["category"],
            params["cashback_pct"],
        )
    if scenario == "floor_per_item":
        shifted = [
            {"price": round(float(i["price"]) * shift, 2), "discount_pct": i["discount_pct"]}
            for i in params["items_pct"]
        ]
        return reference.floor_per_item(shifted)
    if scenario == "points_cap":
        return reference.points_cap_after_discount(
            round(float(params["subtotal"]) * shift, 2),
            params["other_discount_pct"],
            params["cap_pct"],
            params["points_owned"],
        )
    raise ValueError(f"Skenario tak dikenal: {scenario}")


def _scaled(items: List[Dict[str, Any]], shift: float) -> List[Dict[str, Any]]:
    return [{**item, "price": round(float(item["price"]) * shift, 2)} for item in items]


def _subtotal(items: List[Dict[str, Any]], shift: float) -> float:
    return round(sum(float(i["price"]) for i in items) * shift, 2)


# ------------------------------------------------------------------- render
def render_prompt(scenario: str, params: Dict[str, Any], shift: float) -> str:
    """Teks soal Bahasa Indonesia per skenario (angka berformat titik ribuan).

    PENTING (bugfix): semua harga yang DISEBUTKAN di teks soal harus memakai
    nilai ter-shift, agar konsisten dengan expected_output dari reference.
    """
    items_shown = _scaled(params["items"], shift) if "items" in params else None
    if scenario == "tiered_disc":
        return (
            "Toko menerapkan diskon BERTINGKAT. Aturan: (1) member mendapat diskon "
            f"{pct(params['member_pct'])} jika subtotalnya lebih dari {idr(params['member_threshold'])}; "
            f"(2) semua produk kategori '{params['category']}' mendapat diskon TAMBAHAN "
            f"{pct(params['category_extra_pct'])} dari harga jual item tersebut. "
            f"Pelanggan member membeli {_items_text(items_shown)}. "
            "Hitung grand total yang dibayar (jawab angka saja)."
        )
    if scenario == "exclusive":
        return (
            "Aturan EKSKLUSIF: voucher potongan "
            f"{idr(params['voucher'])} dan diskon member {pct(params['member_pct'])} "
            "tidak boleh digabung; sistem otomatis memilih keuntungan terbesar bagi pelanggan. "
            f"Seorang member membeli barang dengan subtotal {idr(_subtotal(params['items'], shift))} "
            "dan hendak memakai voucher. Hitung total akhir (jawab angka saja)."
        )
    if scenario == "min_subtotal_voucher":
        return (
            "Voucher potongan "
            f"{idr(params['voucher'])} berlaku hanya jika subtotal (TIDAK termasuk ongkir) "
            f"minimal {idr(params['min_subtotal'])}. Pelanggan membeli {_items_text(items_shown)} "
            f"dengan ongkir {idr(params['shipping'])}. Hitung total tagihan akhir "
            "(subtotal + ongkir - voucher jika syarat terpenuhi; jawab angka saja)."
        )
    if scenario == "tax_after_discount":
        return (
            "PPN dikenakan {rate} dan WAJIB dihitung dari harga SETELAH diskon, bukan harga normal. "
            "Diskon member"
            f" {pct(params['member_pct'])} berlaku untuk semua item. Pelanggan membeli "
            f"{_items_text(items_shown)}. Hitung total tagihan akhir termasuk PPN (jawab angka saja)."
        ).replace("{rate}", pct(params["tax_rate"]))
    if scenario == "free_shipping_after_voucher":
        return (
            "Gratis ongkir hanya jika subtotal SETELAH diskon/voucher lebih besar dari "
            f"{idr(params['threshold'])}; jika tidak, ongkir {idr(params['shipping'])} tetap dibayar. "
            f"Yang jualan {_items_text(items_shown)} lalu memakai voucher potongan "
            f"{idr(params['voucher'])}. Hitung total tagihan akhir termasuk ongkir "
            "sesuai aturan (jawab angka saja)."
        )
    if scenario == "cashback_category_trap":
        return (
            "Promo cashback "
            f"{pct(params['cashback_pct'])} HANYA untuk produk kategori '{params['category']}' "
            "(dihitung dari subtotal item kategori tersebut saja). Pelanggan membeli: "
            f"{_items_text(items_shown)}. "
            "Hitung total yang harus dibayar setelah cashback (jawab angka saja)."
        )
    if scenario == "floor_per_item":
        harga = ", ".join(
            f"{idr(round(float(i['price']) * shift, 2))}"
            for i in params["items_pct"]
        )
        return (
            "Semua item kena diskon "
            f"{pct(params['items_pct'][0]['discount_pct'])}. Aturan pembulatan: harga final "
            "MASING-MASING item dibulatkan KE BAWAH (floor) ke rupiah penuh, BARU dijumlahkan. "
            f"Harga: {harga}. Hitung total tagihan final (jawab angka saja)."
        )
    if scenario == "points_cap":
        return (
            "Poin (1 poin = Rp1) boleh dipakai sebagai potongan, tetapi maksimal "
            f"{pct(params['cap_pct'])} dari total harga SETELAH diskon, SEBELUM poin. Pelanggan "
            f" memiliki {idr(params['points_owned'])} poin. Subtotal belanja "
            f"{idr(round(float(params['subtotal']) * shift, 2))}, lalu diskon otomatis "
            f"{pct(params['other_discount_pct'])} diterapkan. Hitung total uang yang harus dibayar "
            "(jawab angka saja)."
        )
    raise ValueError(f"template prompt tak dikenal: {scenario}")


def render_prompt_en(scenario: str, params: Dict[str, Any], shift: float) -> str:
    """English mirror of the prompt (same numbers, same expected output)."""
    items_shown = _scaled(params["items"], shift) if "items" in params else None
    if scenario == "tiered_disc":
        return (
            "The store applies TIERED discounts. Rules: (1) a member gets a "
            f"{pct(params['member_pct'])} discount if the subtotal is greater than "
            f"{idr_en(params['member_threshold'])}; (2) every product in the "
            f"'{_category_en(params['category'])}' category gets an ADDITIONAL "
            f"{pct(params['category_extra_pct'])} discount on that item's selling price. "
            f"A member buys {_items_text_en(items_shown)}. "
            "Compute the final grand total the customer pays (answer with the number only)."
        )
    if scenario == "exclusive":
        return (
            "EXCLUSIVE rule: the "
            f"{idr_en(params['voucher'])} voucher and the {pct(params['member_pct'])} "
            "member discount cannot be combined; the system automatically picks the "
            "larger benefit for the customer. A member buys items with a subtotal of "
            f"{idr_en(_subtotal(params['items'], shift))} and wants to use the voucher. "
            "Compute the final total (answer with the number only)."
        )
    if scenario == "min_subtotal_voucher":
        return (
            f"The {idr_en(params['voucher'])} voucher is valid only if the subtotal "
            f"(EXCLUDING shipping) is at least {idr_en(params['min_subtotal'])}. "
            f"A customer buys {_items_text_en(items_shown)} with a shipping fee of "
            f"{idr_en(params['shipping'])}. Compute the final amount (subtotal + "
            "shipping - voucher if the condition is met; answer with the number only)."
        )
    if scenario == "tax_after_discount":
        return (
            f"VAT of {pct(params['tax_rate'])} applies and MUST be calculated on the "
            "price AFTER discount, not on the regular price. A member discount of "
            f"{pct(params['member_pct'])} applies to all items. A customer buys "
            f"{_items_text_en(items_shown)}. Compute the final amount including VAT "
            "(answer with the number only)."
        )
    if scenario == "free_shipping_after_voucher":
        return (
            "Free shipping applies only if the subtotal AFTER discount/voucher is "
            f"greater than {idr_en(params['threshold'])}; otherwise the "
            f"{idr_en(params['shipping'])} shipping fee must still be paid. The customer "
            f"buys {_items_text_en(items_shown)} and then uses a "
            f"{idr_en(params['voucher'])} voucher. Compute the final amount including "
            "shipping according to the rules (answer with the number only)."
        )
    if scenario == "cashback_category_trap":
        return (
            f"A {pct(params['cashback_pct'])} cashback promo applies ONLY to products "
            f"in the '{_category_en(params['category'])}' category (calculated from the "
            "subtotal of those category items only). The customer buys: "
            f"{_items_text_en(items_shown)}. Compute the amount payable after cashback "
            "(answer with the number only)."
        )
    if scenario == "floor_per_item":
        harga = ", ".join(
            f"{idr_en(round(float(i['price']) * shift, 2))}"
            for i in params["items_pct"]
        )
        return (
            f"All items get a {pct(params['items_pct'][0]['discount_pct'])} discount. "
            "Rounding rule: each item's final price is rounded DOWN (floored) to the "
            "nearest whole rupiah FIRST, then summed. "
            f"Prices: {harga}. Compute the final amount (answer with the number only)."
        )
    if scenario == "points_cap":
        return (
            "Points (1 point = Rp1) can be used as a discount, but at most "
            f"{pct(params['cap_pct'])} of the total price AFTER discount, BEFORE points "
            f"are applied. The customer owns {idr_en(params['points_owned'])} points. "
            f"The cart subtotal is {idr_en(round(float(params['subtotal']) * shift, 2))}, "
            f"then an automatic {pct(params['other_discount_pct'])} discount is applied. "
            "Compute the final amount payable (answer with the number only)."
        )
    raise ValueError(f"unknown prompt template: {scenario}")


def render_rules_en(scenario: str, params: Dict[str, Any], shift: float, expected: float) -> str:
    """English mirror of the rules/explanation."""
    base = (
        f"Computed by reference.py (single source of truth). Scenario '{scenario}', "
        f"price shift x{shift}. Expected = {idr_en(expected)}."
    )
    detail = ""
    if scenario == "tiered_disc":
        subtotal = _subtotal(params["items"], shift)
        cat = sum(float(i["price"]) for i in params["items"] if i["category"] == params["category"]) * shift
        detail = (f" Subtotal {idr_en(subtotal)}; member discount {idr_en(subtotal * params['member_pct'])}; "
                  f"category extra {idr_en(cat * params['category_extra_pct'])}.")
    elif scenario == "exclusive":
        subtotal = _subtotal(params["items"], shift)
        detail = (f" Member benefit {idr_en(subtotal * params['member_pct'])} vs voucher "
                  f"{idr_en(params['voucher'])}; pick the larger one.")
    elif scenario == "min_subtotal_voucher":
        subtotal = _subtotal(params["items"], shift)
        applies = subtotal >= params["min_subtotal"]
        detail = (f" Subtotal {idr_en(subtotal)} {'>=' if applies else '<'} minimum "
                  f"{idr_en(params['min_subtotal'])} -> voucher {'APPLIES' if applies else 'FAILS'}.")
    elif scenario == "tax_after_discount":
        subtotal = _subtotal(params["items"], shift)
        after = round(subtotal * (1 - params["member_pct"]), 2)
        detail = f" After discount {idr_en(after)} -> VAT {pct(params['tax_rate'])} -> {idr_en(expected)}."
    elif scenario == "free_shipping_after_voucher":
        subtotal = _subtotal(params["items"], shift)
        after = subtotal - params["voucher"]
        free = after > params["threshold"]
        detail = (f" After voucher {idr_en(after)} {'>' if free else '<='} {idr_en(params['threshold'])} "
                  f"-> shipping {'FREE' if free else 'PAID'}.")
    elif scenario == "cashback_category_trap":
        qualifying = sum(
            float(i["price"]) for i in params["items"]
            if i["category"] == params["category"]
        ) * shift
        detail = (f" Cashback only from items in the '{_category_en(params['category'])}' "
                  f"category ({idr_en(qualifying)} x {pct(params['cashback_pct'])}); "
                  "product names do not matter.")
    elif scenario == "floor_per_item":
        detail = " Floor per item BEFORE summing, not floor of the total."
    elif scenario == "points_cap":
        after = round(float(params["subtotal"]) * shift * (1 - params["other_discount_pct"]), 2)
        cap = round(after * params["cap_pct"], 2)
        detail = (f" Price after discount {idr_en(after)}; points cap {idr_en(cap)} "
                  f"(owned {idr_en(params['points_owned'])} — only min(both) is used).")
    return base + detail


def render_rules(scenario: str, params: Dict[str, Any], shift: float, expected: float) -> str:
    """Penjelasan langkah kalkulasi (dibangkitkan dari referensi param + hasil)."""
    base = (
        f"Dihitung oleh reference.py (single source of truth). Skenario '{scenario}', "
        f"shift harga x{shift}. Expected = {idr(expected)}."
    )
    detail = ""
    if scenario == "tiered_disc":
        subtotal = _subtotal(params["items"], shift)
        cat = sum(float(i["price"]) for i in params["items"] if i["category"] == params["category"]) * shift
        detail = (f" Subtotal {idr(subtotal)}; diskon member {idr(subtotal * params['member_pct'])}; "
                  f"ekstra kategori {idr(cat * params['category_extra_pct'])}.")
    elif scenario == "exclusive":
        subtotal = _subtotal(params["items"], shift)
        detail = (f" Keuntungan member {idr(subtotal * params['member_pct'])} vs voucher "
                  f"{idr(params['voucher'])}; pilih yang terbesar.")
    elif scenario == "min_subtotal_voucher":
        subtotal = _subtotal(params["items"], shift)
        applies = subtotal >= params["min_subtotal"]
        detail = (f" Subtotal {idr(subtotal)} {'>=' if applies else '<'} minimum "
                  f"{idr(params['min_subtotal'])} → voucher {'BERLAKU' if applies else 'GAGAL'}.")
    elif scenario == "tax_after_discount":
        subtotal = _subtotal(params["items"], shift)
        after = round(subtotal * (1 - params["member_pct"]), 2)
        detail = f" Setelah diskon {idr(after)} → PPN {pct(params['tax_rate'])} → {idr(expected)}."
    elif scenario == "free_shipping_after_voucher":
        subtotal = _subtotal(params["items"], shift)
        after = subtotal - params["voucher"]
        free = after > params["threshold"]
        detail = (f" Setelah voucher {idr(after)} {'>' if free else '<='} {idr(params['threshold'])} "
                  f"→ ongkir {'GRATIS' if free else 'DIBAYAR'}.")
    elif scenario == "cashback_category_trap":
        qualifying = sum(
            float(i["price"]) for i in params["items"]
            if i["category"] == params["category"]
        ) * shift
        detail = (f" Cashback hanya dari item kategori '{params['category']}' "
                  f"({idr(qualifying)} x {pct(params['cashback_pct'])}); nama produk tidak berpengaruh.")
    elif scenario == "floor_per_item":
        detail = " Floor per item SEBELUM penjumlahan, bukan floor dari total."
    elif scenario == "points_cap":
        after = round(float(params["subtotal"]) * shift * (1 - params["other_discount_pct"]), 2)
        cap = round(after * params["cap_pct"], 2)
        detail = (f" Harga setelah diskon {idr(after)}; maks poin {idr(cap)} "
                  f"(dimiliki {idr(params['points_owned'])} — hanya min(kedua nilai) yang terpakai).")
    return base + detail


# --------------------------------------------------------------------- main
def generate(schema_path: Path = SCHEMA_PATH, out_path: Path = OUT_PATH,
             lang: str = "id") -> List[Dict[str, Any]]:
    with schema_path.open(encoding="utf-8") as f:
        schema = json.load(f)

    prompt_fn = render_prompt_en if lang == "en" else render_prompt
    rules_fn = render_rules_en if lang == "en" else render_rules

    cases: List[Dict[str, Any]] = []
    for template in schema["templates"]:
        scenario: str = template["scenario"]
        category: str = template["category"]
        shifts: List[float] = template.get("shifts", [1.0])
        for idx, params in enumerate(template["paramsets"]):
            for shift in shifts:
                expected = compute_expected(scenario, params, shift)
                cases.append({
                    "id": f"GEN-{len(cases) + 1:03d}",
                    "prompt": prompt_fn(scenario, params, shift),
                    "expected_output": expected,
                    "rules": rules_fn(scenario, params, shift, expected),
                    "category": category,
                    "scenario": scenario,
                    "paramset": idx,
                    "shift": shift,
                    "lang": lang,
                })

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)
    logger.info("Menulis %d kasus (%s) ke %s", len(cases), lang, out_path)
    return cases


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Generator kasus eval e-commerce")
    parser.add_argument("--schema", default=str(SCHEMA_PATH))
    parser.add_argument("--out", default=None)
    parser.add_argument("--lang", choices=["id", "en"], default="id",
                        help="Bahasa prompt: id (kanonis) atau en (mirror untuk juri)")
    parser.add_argument("--preview", type=int, default=0,
                        help="Tampilkan N kasus pertama tanpa menulis file")
    args = parser.parse_args()

    prompt_fn = render_prompt_en if args.lang == "en" else render_prompt

    if args.preview:
        with Path(args.schema).open(encoding="utf-8") as f:
            schema = json.load(f)
        seen = 0
        for template in schema["templates"]:
            for params in template["paramsets"]:
                for shift in template.get("shifts", [1.0]):
                    expected = compute_expected(template["scenario"], params, shift)
                    print(f"— {template['scenario']} shift={shift} → "
                          f"expected {idr(expected)}")
                    print(f"   {prompt_fn(template['scenario'], params, shift)}")
                    seen += 1
                    if seen >= args.preview:
                        return
    else:
        out_path = Path(args.out) if args.out else (
            OUT_PATH_EN if args.lang == "en" else OUT_PATH)
        cases = generate(Path(args.schema), out_path, lang=args.lang)
        print(f"Selesai: {len(cases)} kasus ({args.lang}) ditulis ke {out_path}")


if __name__ == "__main__":
    main()
