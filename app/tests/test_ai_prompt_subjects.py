import os
import sys
from unittest import TestCase

from app.services.ai.promt import (
    ALLOWED_SUBJECTS,
    QUIZ_PROMPT,
    QUIZ_PROMPT_MISTRAL,
    ai_generator_by_description,
)

TOOL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "tool")


def prompts() -> dict[str, str]:
    return {
        "QUIZ_PROMPT": QUIZ_PROMPT,
        "QUIZ_PROMPT_MISTRAL": QUIZ_PROMPT_MISTRAL,
        "ai_generator_by_description": ai_generator_by_description("Fizika", "mexanika asoslari", 10),
    }


class AllowedSubjectsTests(TestCase):
    def test_every_prompt_lists_all_allowed_subjects(self):
        for name, text in prompts().items():
            with self.subTest(prompt=name):
                for subject in ALLOWED_SUBJECTS:
                    self.assertIn(subject, text)

    def test_no_prompt_ships_an_unsubstituted_placeholder(self):
        for name, text in prompts().items():
            with self.subTest(prompt=name):
                self.assertNotIn("__SUBJECT_RULE__", text)
                self.assertNotIn("{_SUBJECT_LIST}", text)

    def test_extraction_prompts_forbid_inventing_a_subject(self):
        for name in ("QUIZ_PROMPT", "QUIZ_PROMPT_MISTRAL"):
            with self.subTest(prompt=name):
                self.assertIn("Never invent another subject", prompts()[name])

    def test_allowed_subjects_match_the_seeded_catalogue(self):
        """The prompt list and tool/seed_data.py must not drift apart: a subject the
        seed writes but the prompt omits can never be assigned to a generated quiz."""
        sys.path.insert(0, TOOL_DIR)
        try:
            from seed_data import SUBJECTS
        finally:
            sys.path.remove(TOOL_DIR)

        self.assertEqual(
            sorted(ALLOWED_SUBJECTS),
            sorted(subject["name"] for subject in SUBJECTS),
        )

    def test_subject_names_keep_the_database_spelling(self):
        # save_quiz_from_json stores the model's answer verbatim, so a lowercase or
        # translated name would split the catalogue in two.
        for subject in ALLOWED_SUBJECTS:
            with self.subTest(subject=subject):
                self.assertTrue(subject[0].isupper(), subject)
