import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import declarative_base
from app.services import groq_service


# Import the title service with a declarative Base stub so importing tests never
# initializes MySQL or performs any database/network operation.
database_stub = types.ModuleType("app.database")
database_stub.Base = declarative_base()
with patch.dict(sys.modules, {"app.database": database_stub}):
    from app.services import title_generator


class FakeQuery:
    def __init__(self, rows=None, first=None, count=0):
        self.rows = rows or []
        self.first_row = first
        self.count_value = count

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.first_row if self.first_row is not None else (self.rows[0] if self.rows else None)

    def count(self):
        return self.count_value


class FakeDB:
    def __init__(self, product, keywords, competitors, existing=None, duplicate_name_count=1, other_titles=None):
        self.product = product
        self.keywords = keywords
        self.competitors = competitors
        self.existing = existing
        self.duplicate_name_count = duplicate_name_count
        self.other_titles = other_titles or []
        self.product_queries = 0
        self.added = []
        self.commit_count = 0

    def query(self, *entities):
        if len(entities) > 1:
            return FakeQuery(rows=self.other_titles)
        entity = entities[0]
        if entity is title_generator.Product:
            self.product_queries += 1
            if self.product_queries == 1:
                return FakeQuery(first=self.product)
            return FakeQuery(count=self.duplicate_name_count)
        if entity is title_generator.Keyword:
            return FakeQuery(rows=self.keywords)
        if entity is title_generator.CompetitorProduct:
            return FakeQuery(rows=self.competitors)
        if entity is title_generator.FinalProductData:
            return FakeQuery(first=self.existing)
        raise AssertionError(f"Unexpected queried entity: {entity}")

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.commit_count += 1


def groq_response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class GeneratedTitleValidationTests(unittest.TestCase):
    def test_validation_returns_exact_original_name_reason(self):
        self.assertEqual(title_generator.validate_generated_title(
            "VIVA Sport Swimming Cap", "VIVA Sport Swimming Cap", []
        ), (False, "exact_original_name"))

    def test_validation_returns_normalized_same_name_reason(self):
        self.assertEqual(title_generator.validate_generated_title(
            "NIVIA VB492 Spot Volleyball!", "NIVIA VB492 SPOT VOLLEYBALL", []
        ), (False, "same_after_normalization"))

    def test_validation_returns_trivial_change_reason(self):
        self.assertEqual(title_generator.validate_generated_title(
            "VIVA Sport One Color Swimming Cap - Single Color",
            "VIVA Sport One Color Swimming Cap", [],
        ), (False, "trivial_change"))

    def test_validation_returns_changed_product_type_reason(self):
        self.assertEqual(title_generator.validate_generated_title(
            "VIVA Sport Swimming Goggles", "VIVA Sport Swimming Mask", []
        ), (False, "changed_product_type"))

    def test_validation_returns_unsupported_wording_reason(self):
        self.assertEqual(title_generator.validate_generated_title(
            "Everlast Toning Tube Medium Resistance Gym Training",
            "Everlast Toning Tube-Medium Resistance", [], category="Gym Training",
        ), (False, "unsupported_wording"))

    def test_generator_separates_rate_limit_from_title_validation_failure(self):
        class RateLimitError(Exception):
            pass

        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=MagicMock(side_effect=RateLimitError("429 rate limit"))
        )))
        diagnostics = {}
        with patch.object(title_generator, "get_groq_client", return_value=fake_client), \
             patch.object(title_generator.time, "sleep"):
            result = title_generator.generate_title_with_groq(
                "Test Product Type", ["Competitor Product Type"],
                sku_id="RATE-SKU", diagnostics=diagnostics,
            )

        self.assertIsNone(result)
        self.assertEqual(diagnostics["failure_reason"], "rate_limit")
        self.assertEqual(diagnostics["request_count"], 3)
        self.assertEqual(diagnostics["retry_count"], 2)
        self.assertEqual(diagnostics["rate_limit_retry_count"], 2)

    def test_generator_respects_retry_after_header(self):
        class RateLimitError(Exception):
            status_code = 429
            response = SimpleNamespace(status_code=429, headers={"Retry-After": "5"})

        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=MagicMock(side_effect=[
                RateLimitError("too many requests"),
                groq_response("Premier Volley Volleyball"),
            ])
        )))
        diagnostics = {}
        with patch.object(title_generator, "get_groq_client", return_value=fake_client), \
             patch.object(title_generator.time, "sleep") as sleep:
            result = title_generator.generate_title_with_groq(
                "Premier Volley", ["Competitor Volleyball Title"], category="Volleyball",
                sku_id="RETRY-AFTER-SKU", diagnostics=diagnostics,
            )

        self.assertEqual(result, "Premier Volley Volleyball")
        sleep.assert_called_once_with(5.0)
        self.assertEqual(diagnostics["rate_limit_retry_count"], 1)
        self.assertEqual(diagnostics["request_count"], 2)

    def test_groq_client_disables_sdk_retries(self):
        with patch.object(groq_service, "get_groq_api_key", return_value="test-key"), \
             patch.object(groq_service, "Groq") as client_class:
            groq_service.get_groq_client()

        client_class.assert_called_once_with(api_key="test-key", max_retries=0)

    def test_per_sku_request_budget_is_not_reset_between_calls(self):
        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=MagicMock())))
        diagnostics = {"request_count": title_generator.MAX_GROQ_REQUESTS_PER_SKU}
        with patch.object(title_generator, "get_groq_client", return_value=fake_client):
            result = title_generator.generate_title_with_groq(
                "Test Product Type", ["Competitor Product Type"],
                sku_id="BUDGET-SKU", diagnostics=diagnostics,
            )

        self.assertIsNone(result)
        fake_client.chat.completions.create.assert_not_called()
        self.assertEqual(diagnostics["failure_reason"], "retry_exhausted")

    def test_validation_returns_competitor_copy_reason(self):
        copied = "VIVA Sport Swimming Cap for the Pool"
        self.assertEqual(title_generator.validate_generated_title(
            copied, "VIVA Sport Swimming Cap", [copied]
        ), (False, "competitor_title_copy"))

    def test_unchanged_product_name_is_rejected(self):
        self.assertFalse(title_generator.is_valid_generated_title(
            "VIVA Sport Swimming Cap",
            "VIVA Sport Swimming Cap",
            [],
        ))

    def test_rearranged_product_name_without_new_verified_information_is_rejected(self):
        self.assertFalse(title_generator.is_valid_generated_title(
            "Swimming Cap VIVA Sport One Color",
            "VIVA Sport One Color Swimming Cap",
            [],
            category="Swimming Cap",
        ))

    def test_trivial_single_color_addition_is_rejected(self):
        self.assertFalse(title_generator.is_valid_generated_title(
            "VIVA Sport One Color Swimming Cap - Single Color",
            "VIVA Sport One Color Swimming Cap",
            [],
        ))

    def test_exact_competitor_copy_is_rejected(self):
        competitor = "Acme Silicone Swimming Cap for Pool Use"
        self.assertFalse(title_generator.is_valid_generated_title(
            competitor,
            "VIVA Sport Swimming Cap",
            [competitor],
        ))

    def test_near_copy_of_competitor_title_is_rejected(self):
        competitor = "Acme Model X Swimming Cap for Pool Use"
        self.assertFalse(title_generator.is_valid_generated_title(
            "Acme Model X Swimming Cap for Pool Uses",
            "Acme Model X Swimming Cap",
            [competitor],
        ))

    def test_unsupported_claim_is_rejected(self):
        self.assertFalse(title_generator.is_valid_generated_title(
            "VIVA Sport Swimming Mask Waterproof for Open Water",
            "VIVA Sport Swimming Mask",
            ["Professional Swimming Mask for Open Water"],
        ))

    def test_changed_product_type_is_rejected(self):
        self.assertFalse(title_generator.is_valid_generated_title(
            "VIVA Sport Swimming Goggles",
            "VIVA Sport Swimming Mask",
            [],
        ))

    def test_restructured_title_using_verified_target_facts_is_accepted(self):
        product_name = "VIVA Sport One Color Cap Size 5"
        generated = "VIVA Sport Swimming Cap One Color Size 5"
        self.assertTrue(title_generator.is_valid_generated_title(
            generated,
            product_name,
            ["Acme Silicone Swimming Cap for Pool Use"],
            category="Swimming Cap",
        ))

    def test_repeating_existing_product_name_term_without_new_fact_is_rejected(self):
        self.assertFalse(title_generator.is_valid_generated_title(
            "SG Elbow Guard Test Jr. (Kit Product) Kids - Elbow Guard",
            "SG Elbow Guard Test Jr. (Kit Product) Kids",
            [],
            category="Elbow Guard",
        ))

    def test_category_addition_with_new_verified_term_is_accepted(self):
        self.assertTrue(title_generator.is_valid_generated_title(
            "SG RP Ecolite JR Batting Leg Guards Pad",
            "SG Batting Leg guards RP Ecolite JR",
            [],
            category="Batting Pad",
        ))

    def test_competitor_inspired_structure_with_verified_category_is_accepted(self):
        self.assertTrue(title_generator.is_valid_generated_title(
            "SG RP Ecolite JR Batting Leg Guards Pad",
            "SG Batting Leg guards RP Ecolite JR",
            ["Whitedot Cricket Batting Pad, Junior"],
            category="Batting Pad",
        ))

    def test_insufficient_facts_use_manual_review_fallback(self):
        product_name = "VIVA Sport Swimming Cap"
        product = SimpleNamespace(asin="TEST-SKU", product_name=product_name)
        keyword = SimpleNamespace(keyword="stored search suggestion", relevance_score=1.0)
        competitor = SimpleNamespace(competitor_title="Silicone Swimming Cap for Adults", competitor_rank=1)
        db = FakeDB(product, [keyword], [competitor])
        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=MagicMock(side_effect=[groq_response(product_name), groq_response(product_name)])
        )))

        with patch.object(title_generator, "get_groq_client", return_value=fake_client):
            result = title_generator.process_final_product_data_for_asin(db, "TEST-SKU")

        self.assertEqual(fake_client.chat.completions.create.call_count, 2)
        self.assertEqual(result["final_product_title"], "MANUAL_REVIEW_REQUIRED")
        self.assertEqual(result["generation_method"], "manual_review")
        self.assertEqual(db.added[0].final_product_title, "MANUAL_REVIEW_REQUIRED")
        self.assertEqual(db.added[0].all_keywords, ["stored search suggestion"])
        self.assertEqual(db.commit_count, 1)

    def test_duplicate_saved_title_is_rejected_after_targeted_retry(self):
        product_name = "SG Batting Leg guards RP Ecolite JR"
        duplicate_title = "SG RP Ecolite JR Batting Leg Guards Pad"
        product = SimpleNamespace(asin="DUP-SKU", product_name=product_name, category="Batting Pad")
        existing = SimpleNamespace(
            sku_id="DUP-SKU",
            product_name=product_name,
            final_product_title="MANUAL_REVIEW_REQUIRED",
            all_keywords=[],
        )
        competitor = SimpleNamespace(
            competitor_title="Whitedot Cricket Batting Pad, Junior",
            competitor_rank=1,
        )
        db = FakeDB(
            product,
            [],
            [competitor],
            existing=existing,
            other_titles=[(duplicate_title, "OTHER-SKU")],
        )
        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=MagicMock(side_effect=[groq_response(duplicate_title), groq_response(duplicate_title)])
        )))

        with patch.object(title_generator, "get_groq_client", return_value=fake_client):
            result = title_generator.process_final_product_data_for_asin(db, "DUP-SKU")

        self.assertEqual(fake_client.chat.completions.create.call_count, 2)
        self.assertEqual(result["final_product_title"], "MANUAL_REVIEW_REQUIRED")
        self.assertEqual(result["generation_method"], "manual_review")
        self.assertEqual(existing.final_product_title, "MANUAL_REVIEW_REQUIRED")

    def test_ten_manual_review_dry_run_cases(self):
        # Outcomes mirror the read-only ten-product dry run: five products have
        # verified, unique facts sufficient for safe title formatting; five
        # belong to duplicate-name groups and must remain in manual review.
        cases = [
            ("T2YCOSCO000041", "Inline Skate DASH", "Roller Skates", 5, None),
            ("T2YCOSCO000042", "Plastic Stump set - OUT", "Cricket Stumps", 1,
             "Plastic Cricket Stump Set - OUT"),
            ("T2YCOSCO000058", "Premier Volley", "Volleyball", 1,
             "Premier Volley - Volleyball"),
            ("T2YCOSCO000047", "Race Quad Skates - Sr", "Roller Skates", 1,
             "Race Quad Roller Skates - Sr"),
            ("T2YCOSCO000009", "SCOOPER KASHMIR WILLOW CRICKET TENNIS BAT", "Cricket Bat", 1, None),
            ("T2YCOSCO000043", "Shoe Skate SWIFT", "Roller Skates", 3, None),
            ("T2YCOSCO000045", "Shoe Skate SWIFT", "Roller Skates", 3, None),
            ("T2YCOSCO000015", "SIXXER PLASTIC CRICKET TENNIS BAT", "Cricket Bat", 4, None),
            ("T2YCOSCO000016", "SIXXER PLASTIC CRICKET TENNIS BAT", "Cricket Bat", 4, None),
            ("T2YCOSCO000018", "SIXXER PLASTIC CRICKET TENNIS BAT", "Cricket Bat", 4, None),
        ]

        for sku, name, category, duplicate_count, candidate in cases:
            with self.subTest(sku=sku):
                product = SimpleNamespace(asin=sku, product_name=name, category=category)
                existing = SimpleNamespace(
                    sku_id=sku,
                    product_name=name,
                    final_product_title="MANUAL_REVIEW_REQUIRED",
                    all_keywords=["preserved stored keyword"],
                )
                db = FakeDB(
                    product,
                    [SimpleNamespace(keyword="preserved stored keyword", relevance_score=1.0)],
                    [SimpleNamespace(competitor_title="Competitor wording", competitor_rank=1)],
                    existing=existing,
                    duplicate_name_count=duplicate_count,
                )
                create = MagicMock(return_value=groq_response(candidate or "MANUAL_REVIEW_REQUIRED"))
                fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

                with patch.object(title_generator, "get_groq_client", return_value=fake_client):
                    result = title_generator.process_final_product_data_for_asin(db, sku)

                if candidate:
                    self.assertEqual(result["final_product_title"], candidate)
                    self.assertEqual(result["generation_method"], "groq")
                    self.assertEqual(create.call_count, 1)
                    prompt = create.call_args.kwargs["messages"][1]["content"]
                    self.assertIn(f"Target Product Category: {category}", prompt)
                    self.assertNotIn("preserved stored keyword", prompt)
                else:
                    self.assertEqual(result["final_product_title"], "MANUAL_REVIEW_REQUIRED")
                    self.assertEqual(result["generation_method"], "manual_review")
                    self.assertEqual(create.call_count, 0 if duplicate_count > 1 else 2)
                self.assertEqual(existing.all_keywords, ["preserved stored keyword"])
                self.assertEqual(db.commit_count, 1)

    def test_completed_title_is_returned_without_generation_or_write(self):
        product = SimpleNamespace(asin="DONE-SKU", product_name="Verified Product", category="Sports")
        completed = SimpleNamespace(
            sku_id="DONE-SKU",
            product_name="Verified Product",
            final_product_title="Verified Product - Existing Saved Title",
            all_keywords=["kept keyword"],
        )
        db = FakeDB(product, [], [], existing=completed)
        with patch.object(title_generator, "get_groq_client") as groq_client:
            result = title_generator.process_final_product_data_for_asin(db, "DONE-SKU")

        self.assertEqual(result["final_product_title"], completed.final_product_title)
        self.assertEqual(result["generation_method"], "existing")
        self.assertEqual(db.commit_count, 0)
        self.assertEqual(db.added, [])
        groq_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
