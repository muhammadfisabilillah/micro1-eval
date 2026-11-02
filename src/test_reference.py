"""Unit test untuk reference.py — memastikan kalkulator = 8 kasus manual existing.

Jalankan:
    py -m unittest src.test_reference -v
"""

from __future__ import annotations

import unittest

from reference import (
    cashback_category_only,
    exclusive_best_of,
    floor_per_item,
    free_shipping_threshold_after_voucher,
    points_cap_after_discount,
    tax_after_discount,
    tiered_member_and_category,
    voucher_min_subtotal,
)


class TestReferenceAgainstManualCases(unittest.TestCase):
    """8 fungsi harus mereplikasi persis perhitungan manual eval_cases.json."""

    def test_tc001_tiered(self):
        items = [
            {"name": "TV", "category": "Elektronik", "price": 2_000_000},
            {"name": "Buku", "category": "Buku", "price": 100_000},
        ]
        self.assertEqual(
            tiered_member_and_category(items, True, 500_000, 0.15, "Elektronik", 0.10),
            1_585_000,
        )

    def test_tc002_exclusive(self):
        self.assertEqual(exclusive_best_of(300_000, True, 0.10, 50_000), 250_000)

    def test_tc002_member_better(self):
        # Member 30% > voucher 20rb → member menang: 300.000 - 90.000 = 210.000
        self.assertEqual(exclusive_best_of(300_000, True, 0.30, 20_000), 210_000)

    def test_tc003_min_subtotal(self):
        items = [
            {"name": "Sepatu", "category": "Fashion", "price": 35_000},
            {"name": "Topi", "category": "Fashion", "price": 55_000},
        ]
        self.assertEqual(voucher_min_subtotal(items, 15_000, 25_000, 100_000), 105_000)

    def test_tc003_voucher_applies_when_enough(self):
        items = [
            {"name": "X", "category": "Umum", "price": 60_000},
            {"name": "Y", "category": "Umum", "price": 60_000},
        ]
        # Subtotal 120.000 >= 100.000 → voucher dipakai
        self.assertEqual(voucher_min_subtotal(items, 15_000, 25_000, 100_000), 110_000)

    def test_tc004_tax_after_discount(self):
        items = [
            {"name": "A", "category": "Umum", "price": 200_000},
            {"name": "B", "category": "Umum", "price": 300_000},
        ]
        self.assertEqual(tax_after_discount(items, 0.10, 0.11), 499_500)

    def test_tc005_free_shipping_boundary(self):
        items = [
            {"name": "Jaket", "category": "Fashion", "price": 90_000},
            {"name": "Tas", "category": "Fashion", "price": 60_000},
        ]
        self.assertEqual(
            free_shipping_threshold_after_voucher(items, 60_000, 20_000, 100_000),
            110_000,
        )

    def test_tc005_shipping_free_when_above(self):
        items = [
            {"name": "X", "category": "Umum", "price": 100_000},
            {"name": "Y", "category": "Umum", "price": 50_000},
        ]
        # Setelah voucher 50rb → 100.000 TIDAK > 100.000 (boundary ketat: harus >)
        self.assertEqual(
            free_shipping_threshold_after_voucher(items, 50_000, 20_000, 100_000),
            120_000,
        )

    def test_tc006_cashback_category_binding(self):
        items = [
            {"name": "TV", "category": "Elektronik", "price": 500_000},
            {"name": "Elektronik untuk Pemula", "category": "Buku", "price": 100_000},
            {"name": "Sprei", "category": "Rumah Tangga", "price": 100_000},
        ]
        self.assertEqual(cashback_category_only(items, "Elektronik", 0.10), 650_000)

    def test_tc007_floor_per_item(self):
        items = [
            {"price": 15_999, "discount_pct": 0.125},
            {"price": 45_555, "discount_pct": 0.125},
            {"price": 77_777, "discount_pct": 0.125},
        ]
        self.assertEqual(floor_per_item(items), 121_913)

    def test_tc008_points_cap(self):
        self.assertEqual(points_cap_after_discount(100_000, 0.10, 0.50, 80_000), 45_000)

    def test_tc008_owned_points_below_cap(self):
        # Poin milik kurang dari cap → semua terpakai: 90.000 - 30.000 = 60.000
        self.assertEqual(points_cap_after_discount(100_000, 0.10, 0.50, 30_000), 60_000)


if __name__ == "__main__":
    unittest.main()
