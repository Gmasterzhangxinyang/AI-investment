from __future__ import annotations

import unittest
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.skills.convertible_bond_ranking.handler import rank_convertible_bonds


class CommercialComponentTests(unittest.TestCase):
    def test_convertible_bond_ranking_filters_price_and_penalizes_negative_ytm(self) -> None:
        data = pd.DataFrame(
            [
                {
                    "bond_code": "A",
                    "bond_name": "A转债",
                    "price": 120,
                    "remaining_years": 1.0,
                    "conversion_premium_rate": 0.1,
                    "ytm": 0.02,
                    "stock_code": "S1",
                    "stock_name": "正股A",
                    "deducted_profit_growth": 0.2,
                    "notes": "",
                },
                {
                    "bond_code": "B",
                    "bond_name": "B转债",
                    "price": 130,
                    "remaining_years": 2.0,
                    "conversion_premium_rate": 0.2,
                    "ytm": -0.01,
                    "stock_code": "S2",
                    "stock_name": "正股B",
                    "deducted_profit_growth": 0.1,
                    "notes": "",
                },
                {
                    "bond_code": "C",
                    "bond_name": "C转债",
                    "price": 145,
                    "remaining_years": 0.5,
                    "conversion_premium_rate": 0.05,
                    "ytm": 0.03,
                    "stock_code": "S3",
                    "stock_name": "正股C",
                    "deducted_profit_growth": 0.3,
                    "notes": "",
                },
            ]
        )
        params = {
            "convertible_bond": {
                "price_limit": 140,
                "negative_ytm_penalty": 15,
                "score_weights": {
                    "deducted_profit_growth": 0.3,
                    "remaining_years": 0.3,
                    "conversion_premium_rate": 0.3,
                    "ytm": 0.1,
                },
            }
        }

        ranked = rank_convertible_bonds(data, params)

        self.assertEqual(list(ranked["bond_code"]), ["A", "B"])
        self.assertGreater(float(ranked.iloc[0]["score"]), float(ranked.iloc[1]["score"]))
        self.assertIn("已扣分", ranked.iloc[1]["rank_reason"])


if __name__ == "__main__":
    unittest.main()
