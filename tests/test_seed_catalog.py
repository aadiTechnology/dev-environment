"""Validate the CRM seed catalog and the idempotent field comparison."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

DEV = Path(__file__).resolve().parents[1]
CATALOG = json.loads((DEV / "seeds" / "crm_seed.json").read_text(encoding="utf-8"))
CRM_SEED = (
    DEV.parent
    / "Product"
    / "aadi-crm"
    / "backend"
    / "scripts"
    / "seed_development_projects.py"
)
CP_SEED = (
    DEV.parent
    / "MultiTenant"
    / "Aadi-MultiTenant-Platform"
    / "backend"
    / "scripts"
    / "seed_development_tenant.py"
)

COMMON_LABELS = [
    "Contact / Record Name",
    "Contact Person",
    "Phone Number",
    "Lead Source",
    "Status",
    "Priority",
    "Last Contact Date",
    "Next Follow-up Date",
    "Expected Value",
    "Notes",
]
DOMAIN = {
    "PRESCHOOL": ["Number of Students", "Number of Branches", "Product of Interest"],
    "PANEERWALA": ["Product / Variant", "Quantity", "Order Amount", "Payment Status"],
    "SPACE-VIEW": ["Service Type", "Service Location", "Requirement Details"],
    "HIRING": ["Position Applied For", "Recruitment Stage", "Recruitment Outcome"],
}


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SeedCatalogTest(unittest.TestCase):
    def test_projects_and_common_fields(self) -> None:
        self.assertEqual([item["code"] for item in CATALOG["projects"]], list(DOMAIN))
        self.assertEqual(CATALOG["phone_field_type"], "mobile")
        for project in CATALOG["projects"]:
            fields = CATALOG["common_fields"] + project["extra_fields"]
            self.assertEqual([field["label"] for field in fields[:10]], COMMON_LABELS)
            self.assertEqual(
                [field["label"] for field in fields[10:]],
                DOMAIN[project["code"]],
            )
            self.assertEqual(fields[2]["field_key"], "phone_number")
            self.assertEqual(fields[2]["field_type"], "mobile")
            self.assertTrue(fields[2]["required"])
            self.assertTrue(fields[4]["required"])
            self.assertGreaterEqual(len(project["records"]), 3)

    def test_dropdowns_and_record_variety(self) -> None:
        by_key = {field["field_key"]: field for field in CATALOG["common_fields"]}
        self.assertEqual(
            [label for _value, label in by_key["lead_source"]["options"]],
            ["Website", "Phone Call", "WhatsApp", "Referral", "Social Media", "Walk-in", "Other"],
        )
        self.assertEqual(
            [label for _value, label in by_key["status"]["options"]],
            ["New", "Contacted", "Interested", "In Progress", "Converted", "Lost", "On Hold"],
        )
        self.assertEqual(
            [label for _value, label in by_key["priority"]["options"]],
            ["Low", "Medium", "High"],
        )
        statuses = set()
        follow_ups = []
        keys = []
        for project in CATALOG["projects"]:
            keys.extend(record["seed_key"] for record in project["records"])
            for record in project["records"]:
                statuses.add(record["values"]["status"])
                if record["values"].get("next_follow_up_date"):
                    follow_ups.append(record["values"]["next_follow_up_date"])
        self.assertIn("new", statuses)
        self.assertIn("in_progress", statuses)
        self.assertIn("converted", statuses)
        self.assertTrue(any(item > "2026-10-25" for item in follow_ups))
        self.assertIn("2026-10-01", follow_ups)
        self.assertEqual(len(keys), len(set(keys)))

    def test_domain_values_do_not_collapse_money_or_hiring(self) -> None:
        paneer = next(item for item in CATALOG["projects"] if item["code"] == "PANEERWALA")
        order = next(item for item in paneer["records"] if item["seed_key"] == "paneerwala-01")
        self.assertNotEqual(order["values"]["expected_value"], order["values"]["order_amount"])
        hiring = next(item for item in CATALOG["projects"] if item["code"] == "HIRING")
        self.assertIn("Recruitment Stage", hiring["description"])
        hired = next(item for item in hiring["records"] if item["seed_key"] == "hiring-03")
        self.assertEqual(hired["values"]["status"], "converted")
        self.assertEqual(hired["values"]["recruitment_stage"], "hired")
        self.assertEqual(hired["values"]["recruitment_outcome"], "hired")
        positions = next(field for field in hiring["extra_fields"] if field["field_key"] == "position_applied_for")
        self.assertIn(("interior_designer", "Interior Designer"), [tuple(item) for item in positions["options"]])

    def test_field_comparison_is_idempotent(self) -> None:
        crm = load(CRM_SEED, "crm_seed")
        fields = CATALOG["common_fields"] + CATALOG["projects"][0]["extra_fields"]
        existing = []
        for position, spec in enumerate(fields, start=1):
            item = {
                "field_key": spec["field_key"],
                "label": spec["label"],
                "field_type": spec["field_type"],
                "required": spec["required"],
                "section_name": spec["section_name"],
                "position": position,
            }
            if spec.get("options"):
                item["options"] = [{"value": value, "label": label} for value, label in spec["options"]]
            if spec.get("currency_code"):
                item["currency_code"] = spec["currency_code"]
            existing.append(item)
        self.assertEqual(crm.compare_fields(existing, fields), "match")
        self.assertEqual(crm.compare_fields([], fields), "prefix")
        changed = [dict(item) for item in existing]
        changed[0]["label"] = "Other name"
        self.assertEqual(crm.compare_fields(changed, fields), "conflict")
        first = crm.plan_actions(set(), ["preschool-01", "preschool-02"])
        second = crm.plan_actions(set(first["create"]), ["preschool-01", "preschool-02"])
        self.assertEqual(second["create"], [])
        self.assertEqual(second["reuse"], ["preschool-01", "preschool-02"])

    def test_registration_gaps_do_not_replace_a_superset(self) -> None:
        control = load(CP_SEED, "control_seed")
        self.assertIsNone(control.registration_gaps(None))
        complete = {
            "features": [{"key": key} for key in control.REQUIRED_FEATURES] + [{"key": "extra"}],
            "permissions": [{"key": key} for key in control.REQUIRED_PERMISSIONS],
        }
        self.assertEqual(control.registration_gaps(complete), [])
        incomplete = {
            "features": [{"key": "lead_management"}],
            "permissions": [{"key": "crm.lead_management.read"}],
        }
        self.assertTrue(control.registration_gaps(incomplete))
        actions = control.plan_actions(set(control.REQUIRED_FEATURES), list(control.REQUIRED_FEATURES))
        self.assertEqual(actions["create"], [])


if __name__ == "__main__":
    unittest.main()
