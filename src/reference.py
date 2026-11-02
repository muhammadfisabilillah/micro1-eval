"""Reference Implementation — kalkulator Python murni (Single Source of Truth).

Semua fungsi di sini TIDAK menggunakan AI sama sekali: murni aritmetika dengan
aturan bisnis e-commerce yang sudah distandarkan. `generator.py` memanggil
fungsi-fungsi ini untuk menghitung `expected_output` secara otomatis, dan
`test_reference.py` memverifikasinya terhadap 8 kasus manual di
data/eval_cases.json.

Semua fungsi: input dict/dsipatch angka bersih (rupiah float), output rupiah
float dibulatkan maksimal 2 desimal. Tidak ada state, tidak ada I/O — murni
pura fungsi, mudah di-enterprise-test.
"""

from __future__ import annotations

import math
from typing import Dict, List

Item = Dict[str, object]  # {"name": str, "category": str, "price": float}

RUP: float = 0.01  # toleransi rupiah (dibulatkan ke 2 desimal ratus rupiah)


def _round_rupiah(value: float) -> float:
    return round(value, 2)


def tiered_member_and_category(
    items: List[Item],
    member: bool,
    member_threshold: float,
    member_pct: float,
    category: str,
    category_extra_pct: float,
) -> float:
    """Diskon BERTINGKAT ala TC-001.

    Urutan (sudah disepakati aturan resmi eval — jebakan "ordering"):
    1. Jika member & subtotal > threshold: potong member_pct x SUBTOTAL.
    2. Setelahnya, potong category_extra_pct x (subtotal item kategori itu saja,
       harga ASLI, bukan setelah diskonSteps pertama).
    """
    subtotal = sum(float(i["price"]) for i in items)
    total = subtotal
    if member and subtotal > member_threshold:
        total -= subtotal * member_pct
    cat_total = sum(float(i["price"]) for i in items if str(i["category"]) == category)
    total -= cat_total * category_extra_pct
    return _round_rupiah(total)


def exclusive_best_of(
    subtotal: float,
    member: bool,
    member_pct: float,
    voucher: float,
) -> float:
    """Aturan eksklusif (TC-002): voucher vs diskon member, tidak bisa digabung.

    Sistem memilih keuntungan terbesar bagi pelanggan.
    """
    member_benefit = subtotal * member_pct if member else 0.0
    benefit = max(member_benefit, voucher)
    return _round_rupiah(subtotal - benefit)


def voucher_min_subtotal(
    items: List[Item],
    shipping: float,
    voucher: float,
    min_subtotal: float,
) -> float:
    """Voucher valid hanya jika SUBTOTAL (tanpa ongkir) >= min_subtotal (TC-003).

    Potongan dihitung pada subtotal; ongkir selalu ditambahkan.
    """
    subtotal = sum(float(i["price"]) for i in items)
    applies = subtotal >= min_subtotal
    total = subtotal + shipping - (voucher if applies else 0.0)
    return _round_rupiah(total)


def tax_after_discount(
    items: List[Item],
    member_pct: float,
    tax_rate: float,
) -> float:
    """PPN dihitung dari harga SETELAH diskon (TC-004, jebakan 'tax-base')."""
    subtotal = sum(float(i["price"]) for i in items)
    after = subtotal * (1.0 - member_pct)
    return _round_rupiah(after * (1.0 + tax_rate))


def free_shipping_threshold_after_voucher(
    items: List[Item],
    voucher: float,
    shipping: float,
    threshold: float,
) -> float:
    """Gratis ongkir hanya jika subtotal SETELAH voucher > threshold (TC-005).

    Potongan voucher selalu berlaku di mana pun syarat ongkir terpenuhi.
    """
    subtotal = sum(float(i["price"]) for i in items)
    after = subtotal - voucher
    shipping_due = 0.0 if after > threshold else shipping
    return _round_rupiah(after + shipping_due)


def cashback_category_only(
    items: List[Item],
    category: str,
    cashback_pct: float,
) -> float:
    """Cashback % hanya untuk item kategori tertentu (TC-006).

    Jebakan 'category-binding': nama item lain bisa mengandung kata kategori
    tapi kategorinya berbeda (mis. buku 'Elektronik untuk Pemula').
    """
    qualifying = sum(
        float(i["price"]) for i in items if str(i["category"]) == category
    )
    total = sum(float(i["price"]) for i in items)
    return _round_rupiah(total - qualifying * cashback_pct)


def floor_per_item(
    items: List[Dict[str, float]],
) -> float:
    """Diskon per item lalu FLOOR masing-masing harga sebelum dijumlahkan (TC-007).

    items: [{"price": float, "discount_pct": float}, ...]
    Jebakan 'rounding': menjumlah dulu lalu floor menghasilkan selisih 1-2 rupiah.
    """
    total = sum(
        math.floor(float(i["price"]) * (1.0 - float(i["discount_pct"])))
        for i in items
    )
    return _round_rupiah(float(total))


def points_cap_after_discount(
    subtotal: float,
    other_discount_pct: float,
    cap_pct: float,
    points_owned: float,
) -> float:
    """Poin (1 poin = Rp1) maksimal cap_pct x total SETELAH diskon (TC-008).

    Poin yang dipakai = min(points_owned, cap_pct x harga-setelah-diskon).
    Jebakan 'points': AI memakai seluruh poin atau cap dari poin milik user.
    """
    after = subtotal * (1.0 - other_discount_pct)
    usable = min(points_owned, after * cap_pct)
    return _round_rupiah(after - usable)
