from unittest import TestCase

from app.services.ai.promt import QUIZ_SCHEMA, QUIZ_SCHEMA_MISTRAL
from app.services.ai.subjects import (
    ALLOWED_SUBJECTS,
    canonical_subject,
    resolve_quiz_subject,
)


def payload(subject=None, question_subjects=()):
    return {
        "quiz_title": "Test",
        "subject": subject,
        "questions": [{"subject": value} for value in question_subjects],
    }


class SchemaEnumTests(TestCase):
    def test_both_schemas_restrict_the_subject_field(self):
        cases = {
            "gemini root": QUIZ_SCHEMA["properties"]["subject"],
            "gemini question": QUIZ_SCHEMA["properties"]["questions"]["items"]["properties"]["subject"],
            "mistral root": QUIZ_SCHEMA_MISTRAL["properties"]["subject"],
            "mistral question": QUIZ_SCHEMA_MISTRAL["properties"]["questions"]["items"]["properties"]["subject"],
        }
        for name, field in cases.items():
            with self.subTest(field=name):
                self.assertEqual(field["enum"], list(ALLOWED_SUBJECTS))


class CanonicalSubjectTests(TestCase):
    def test_catalogue_names_pass_through(self):
        for subject in ALLOWED_SUBJECTS:
            with self.subTest(subject=subject):
                self.assertEqual(canonical_subject(subject), subject)

    def test_casing_and_spacing_are_normalised(self):
        for value in ("matematika", "  MATEMATIKA  ", "MaTeMaTiKa"):
            with self.subTest(value=value):
                self.assertEqual(canonical_subject(value), "Matematika")

    def test_uzbek_apostrophe_variants_resolve(self):
        for value in ("o‘zbek tili", "o'zbek tili", "oʻzbek tili", "o`zbek tili"):
            with self.subTest(value=value):
                self.assertEqual(canonical_subject(value), "Ona tili va adabiyoti")

    def test_topic_names_resolve_to_their_subject(self):
        cases = {
            "Algebra": "Matematika",
            "geometriya": "Matematika",
            "Mexanika": "Fizika",
            "Organik kimyo": "Kimyo",
            "Anatomiya": "Biologiya",
            "Vatan tarixi": "Tarix",
            "Adabiyot": "Ona tili va adabiyoti",
            "English": "Ingliz tili",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(canonical_subject(value), expected)

    def test_a_subject_named_inside_a_longer_label_still_resolves(self):
        self.assertEqual(canonical_subject("Matematika (algebra)"), "Matematika")
        self.assertEqual(canonical_subject("9-sinf fizika"), "Fizika")

    def test_unknown_and_empty_values_do_not_resolve(self):
        for value in (None, "", "   ", "Informatika", "Chizmachilik"):
            with self.subTest(value=value):
                self.assertIsNone(canonical_subject(value))


class ResolveQuizSubjectTests(TestCase):
    def test_the_models_own_answer_wins(self):
        self.assertEqual(resolve_quiz_subject(payload("Kimyo", ["Fizika"])), "Kimyo")

    def test_an_unusable_root_falls_back_to_the_questions(self):
        data = payload("Informatika", ["Fizika", "Mexanika", "Kimyo"])

        self.assertEqual(resolve_quiz_subject(data), "Fizika")

    def test_the_picked_subject_is_used_when_nothing_else_resolves(self):
        data = payload("Informatika", ["Informatika"])

        self.assertEqual(resolve_quiz_subject(data, fallback="Biologiya"), "Biologiya")

    def test_an_unresolvable_quiz_is_rejected_rather_than_stored(self):
        with self.assertRaises(ValueError) as raised:
            resolve_quiz_subject(payload("Informatika"))

        self.assertIn("Test fani aniqlanmadi", str(raised.exception))

    def test_the_result_is_never_empty_and_always_from_the_catalogue(self):
        cases = [
            payload("Matematika"),
            payload(None, ["algebra"]),
            payload("", ["", "Kimyo"]),
            payload("Informatika", [], ),
        ]
        for index, data in enumerate(cases):
            with self.subTest(case=index):
                try:
                    resolved = resolve_quiz_subject(data, fallback="Tarix")
                except ValueError:
                    self.fail("fallback berilgan holatda xato bo'lmasligi kerak")
                self.assertIn(resolved, ALLOWED_SUBJECTS)
                self.assertTrue(resolved)
