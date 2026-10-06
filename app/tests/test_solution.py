import copy
from unittest import TestCase

from app.services.solution.client import ModelReply, SolutionModelError
from app.services.solution.generator import explain_bank_question, solve_problem
from app.services.solution.prompts import explain_bank_prompt
from app.services.solution.schema import SOLUTION_SCHEMA
from app.services.solution.validator import normalize, validate


def solution(chosen="B", **overrides):
    """A reply that passes every rule; tests break one thing at a time."""
    data = {
        "problem_ok": True,
        "problem_note": None,
        "kind": "math",
        "asked": "Progressiyaning ayirmasini topamiz.",
        "plan": ["Formulani yozamiz", "Hisoblaymiz"],
        "values": [
            {"name": "a_5", "label": "beshinchi had", "value": "15", "color": 1},
            {"name": "a_10", "label": "o‘ninchi had", "value": "30", "color": 2},
        ],
        "given": [],
        "find": [],
        "formula": None,
        "tape": None,
        "steps": [
            {
                "title": "Formulani yozamiz",
                "say": "Har bir had oldingisidan $d$ ga katta.",
                "board": [{"tex": r"a_n = a_1 + (n-1)d", "role": "formula"}],
                "summary": "had formulasi",
                "tip": None,
                "simpler": ["Har qadamda bir xil son qo‘shiladi."],
                "rule": None,
            },
            {
                "title": "Hisoblaymiz",
                "say": "Ikkinchi tenglamadan birinchisini ayiramiz.",
                "board": [
                    {"tex": r"\hlb{30} - \hla{15} = 5d", "role": "step"},
                    {"tex": r"d = 3", "role": "result"},
                ],
                "summary": "d = 3",
                "tip": None,
                "simpler": ["30 dan 15 ni ayirsak 15 bo‘ladi."],
                "rule": None,
            },
        ],
        "answer": {"tex": "d = 3", "value": "3", "words": "uch", "unit": None},
        "check": None,
        "shortcut": None,
        "real_life": None,
        "chosen_option": chosen,
        "hints": [
            {"option": label, "headline": "Kichik xato.", "right_tex": "d = 3",
             "wrong_tex": "d = 2", "why": "Ayirma 5 ga bo‘linadi.", "tip": "Tekshiring."}
            for label in "ABCD" if label != chosen
        ],
    }
    data.update(overrides)
    return data


class FakeClient:
    """Plays back prepared replies and records what it was asked."""

    model = "fake-model"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def solve(self, prompt, *, images=(), previous=None, repair=None, temperature=0.2, deadline=None):
        self.calls.append({"prompt": prompt, "repair": repair, "temperature": temperature, "deadline": deadline})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return ModelReply(data=copy.deepcopy(reply), raw="{}", model=self.model, latency_ms=10)


OPTIONS = [("A", "2", False), ("B", "3", True), ("C", "5", False), ("D", "15", False)]


def explain(client):
    return explain_bank_question(
        client, subject="matematika", question="a5 = 15, a10 = 30. d = ?",
        table=None, options=OPTIONS, image_paths=[],
    )


class ValidatorTests(TestCase):
    def test_a_clean_reply_passes(self):
        verdict = validate(normalize(solution()), option_labels=list("ABCD"))
        self.assertTrue(verdict.ok, verdict.all())

    def test_a_broken_escape_is_caught(self):
        # A lone "\v" in the model's JSON once arrived as a line break + "v1".
        data = solution()
        data["steps"][1]["board"][0]["tex"] = "\x0bhlb{30} - 15 = 5d"
        self.assertTrue(any("control character" in e for e in validate(data).hard))

    def test_dollar_signs_on_the_board_are_rejected(self):
        data = solution()
        data["steps"][0]["board"][0]["tex"] = r"\text{Birinchi kun: } $x$ \text{ kg}"
        self.assertTrue(any("remove every $" in e for e in validate(normalize(data)).hard))

    def test_colour_marks_outside_inline_maths_are_rejected(self):
        data = solution(asked=r"Jami \hla{175} kg sotilgan.")
        self.assertTrue(any("only inside $...$" in e for e in validate(data).hard))

    def test_a_colour_mark_needs_a_value_with_that_colour(self):
        data = solution()
        data["steps"][1]["board"][0]["tex"] = r"\hlc{30} - 15 = 5d"
        self.assertTrue(any("colour 3 is marked" in e for e in validate(data).hard))

    def test_the_plan_has_one_item_per_step(self):
        data = solution(plan=["Faqat bitta"])
        self.assertTrue(any("one plan item per step" in e for e in validate(data).hard))

    def test_a_long_sentence_is_only_a_soft_problem(self):
        data = solution()
        data["steps"][0]["say"] = " ".join(["so‘z"] * 30) + "."
        verdict = validate(data)
        self.assertTrue(verdict.usable)
        self.assertTrue(verdict.soft)

    def test_physics_needs_given_and_find(self):
        verdict = validate(solution(kind="physics"))
        self.assertIn("physics: given is empty", verdict.hard)
        self.assertIn("physics: find is empty", verdict.hard)


class BankGeneratorTests(TestCase):
    def test_the_prompt_never_names_the_correct_option(self):
        # Told the answer, the model would simply agree and the key check below
        # would prove nothing.
        prompt = explain_bank_prompt(
            subject="matematika", question="d = ?", table=None,
            options=[(label, text) for label, text, _ in OPTIONS],
        )
        self.assertNotIn("is_correct", prompt)
        self.assertNotIn("True", prompt)
        self.assertIn("You are NOT told which option is correct", prompt)

    def test_a_solution_that_lands_on_the_key_is_kept(self):
        outcome = explain(FakeClient([solution("B")]))
        self.assertTrue(outcome.ok)
        self.assertTrue(outcome.matches_key)
        self.assertEqual(outcome.rounds, 1)

    def test_two_solutions_agreeing_against_the_key_become_a_dispute(self):
        client = FakeClient([solution("A"), solution("A")])
        outcome = explain(client)
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.payload, {"disputed": {"model_option": "A", "key": "B"}})
        # The second round is a genuinely independent try.
        self.assertGreater(client.calls[1]["temperature"], client.calls[0]["temperature"])

    def test_disagreeing_rounds_are_a_plain_rejection(self):
        outcome = explain(FakeClient([solution("A"), solution("C")]))
        self.assertFalse(outcome.ok)
        self.assertIsNone(outcome.payload)

    def test_a_broken_reply_is_repaired_once(self):
        broken = solution("B", plan=["bitta"])
        client = FakeClient([broken, solution("B")])
        outcome = explain(client)
        self.assertTrue(outcome.ok)
        self.assertIn("one plan item per step", client.calls[1]["repair"])

    def test_an_outage_is_not_a_rejection(self):
        outcome = explain(FakeClient([SolutionModelError("503")]))
        self.assertFalse(outcome.ok)
        self.assertTrue(outcome.error.startswith("model unavailable"))

    def test_a_question_without_exactly_one_key_is_never_sent(self):
        client = FakeClient([])
        outcome = explain_bank_question(
            client, subject="matematika", question="?", table=None,
            options=[("A", "1", False), ("B", "2", False)], image_paths=[],
        )
        self.assertFalse(outcome.ok)
        self.assertEqual(client.calls, [])


class FreeSolveTests(TestCase):
    def test_an_unsolvable_problem_carries_a_note_for_the_student(self):
        reply = solution(problem_ok=False, problem_note="Massa berilmagan.")
        outcome = solve_problem(FakeClient([reply]), subject="fizika", problem="Kuchni toping.")
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.payload, {"note": "Massa berilmagan."})

    def test_bank_only_fields_are_dropped(self):
        outcome = solve_problem(FakeClient([solution(None, hints=[])]), subject="matematika", problem="d = ?")
        self.assertTrue(outcome.ok)
        self.assertNotIn("hints", outcome.payload)
        self.assertNotIn("chosen_option", outcome.payload)


class SchemaTests(TestCase):
    def test_steps_come_before_the_answer_and_the_answer_before_the_option(self):
        # Generated in this order, the model commits to a derivation before it
        # looks at the options.
        order = SOLUTION_SCHEMA["propertyOrdering"]
        self.assertLess(order.index("steps"), order.index("answer"))
        self.assertLess(order.index("answer"), order.index("chosen_option"))


class NormalizeTests(TestCase):
    def test_line_breaks_inside_prose_are_flattened(self):
        # Seen from the model: "jami \n\n$175$ kg", which split a sentence.
        data = normalize(solution(asked="Do‘kon jami \n\n$175$ kg sotdi."))
        self.assertEqual(data["asked"], "Do‘kon jami $175$ kg sotdi.")

    def test_outer_dollars_are_stripped_from_tex_fields(self):
        data = solution()
        data["answer"]["tex"] = "$d = 3$"
        self.assertEqual(normalize(data)["answer"]["tex"], "d = 3")


class DecimalCommaTests(TestCase):
    def test_decimals_take_the_school_comma_on_the_board_and_in_words(self):
        # Captured: a bar of "1.5x" and "0.625x" and a summary "1.5x, 0.625x".
        data = solution(tape={"total": "175 kg", "parts": [
            {"label": "1-kun", "expr": "1.5x", "weight": 1.5},
            {"label": "2-kun", "expr": "0.625x", "weight": 0.625},
        ]})
        data["steps"][1]["board"][1]["tex"] = r"x = \frac{175}{3.125}"
        data["steps"][1]["summary"] = "Ikkinchi kun: 1.5x, birinchi: $0.625x$."
        data = normalize(data)
        self.assertEqual([p["expr"] for p in data["tape"]["parts"]], ["1{,}5x", "0{,}625x"])
        self.assertEqual(data["steps"][1]["board"][1]["tex"], r"x = \frac{175}{3{,}125}")
        self.assertEqual(data["steps"][1]["summary"], "Ikkinchi kun: 1,5x, birinchi: $0{,}625x$.")

    def test_a_sentence_ending_before_a_number_is_left_alone(self):
        self.assertEqual(normalize(solution(asked="Javob 3. Keyin 4 ni olamiz."))["asked"],
                         "Javob 3. Keyin 4 ni olamiz.")


class ProviderErrorTests(TestCase):
    """The SDK raises 429 as a ClientError; the client must tell a spent day apart."""

    def _client_raising(self, exc):
        from app.services.solution.client import SolutionClient

        class _Models:
            def generate_content(self, **kwargs):
                raise exc

        client = SolutionClient.__new__(SolutionClient)
        client.model = "fake"
        client._client = type("C", (), {"models": _Models()})()
        return client

    def _client_error(self, code, message):
        from google.genai.errors import ClientError

        return ClientError(code, {"error": {"code": code, "message": message, "status": "X"}})

    def test_a_daily_quota_is_reported_as_such_and_not_retried(self):
        from app.services.solution.client import SolutionQuotaError

        client = self._client_raising(self._client_error(
            429, "Quota exceeded ... quotaId GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
        with self.assertRaises(SolutionQuotaError):
            client.recognize(b"img", "image/jpeg")

    def test_a_rejected_request_is_not_a_quota_problem(self):
        from app.services.solution.client import SolutionModelError, SolutionQuotaError

        client = self._client_raising(self._client_error(400, "Request contains an invalid argument."))
        with self.assertRaises(SolutionModelError) as caught:
            client.recognize(b"img", "image/jpeg")
        self.assertNotIsInstance(caught.exception, SolutionQuotaError)

    def test_the_failure_line_says_which_promise_to_make(self):
        from app.services.solution.client import SolutionModelError, SolutionQuotaError
        from app.services.solution.generator import model_failure

        self.assertTrue(model_failure(SolutionQuotaError("x")).startswith("model quota"))
        self.assertTrue(model_failure(SolutionModelError("x")).startswith("model unavailable"))

    def test_recognition_sends_no_thinking_budget(self):
        # A budget of 0 is rejected by the newer models with 400.
        from unittest.mock import patch

        from app.services.solution.client import SolutionClient

        client = SolutionClient.__new__(SolutionClient)
        client.model = "fake"
        with patch.object(SolutionClient, "_call", return_value="ok") as call:
            client.recognize(b"img", "image/jpeg")
        self.assertIsNone(call.call_args.kwargs["thinking"])


class FallbackTests(TestCase):
    """A spent or withdrawn model hands the problem to the next one."""

    def _client(self, outcomes):
        from app.services.solution.client import SolutionClient

        client = SolutionClient.__new__(SolutionClient)
        client.model = "main"
        tried = []

        def fake_call(contents, **kwargs):
            tried.append(kwargs["model"])
            outcome = outcomes[kwargs["model"]]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        client._call = fake_call
        return client, tried

    def test_a_spent_quota_moves_on_to_the_next_model(self):
        from unittest.mock import patch

        from app.services.solution.client import SolutionQuotaError

        client, tried = self._client({"main": SolutionQuotaError("PerDay"), "second": "reply"})
        with patch("app.services.solution.client.settings.SOLUTION_FALLBACK_MODELS", "second,third"):
            self.assertEqual(client.solve("p"), "reply")
        self.assertEqual(tried, ["main", "second"])

    def test_a_withdrawn_model_moves_on_too(self):
        from unittest.mock import patch

        from app.services.solution.client import SolutionModelError

        client, tried = self._client({"main": SolutionModelError("404 NOT_FOUND"), "second": "reply"})
        with patch("app.services.solution.client.settings.SOLUTION_FALLBACK_MODELS", "second"):
            self.assertEqual(client.solve("p"), "reply")

    def test_a_model_still_busy_after_its_retries_hands_over(self):
        # _call has already retried; 503 reaching here means a long busy spell.
        from unittest.mock import patch

        from app.services.solution.client import SolutionModelError

        client, tried = self._client({"main": SolutionModelError("503 UNAVAILABLE"), "second": "reply"})
        with patch("app.services.solution.client.settings.SOLUTION_FALLBACK_MODELS", "second"):
            self.assertEqual(client.solve("p"), "reply")
        self.assertEqual(tried, ["main", "second"])

    def test_a_bad_request_is_not_retried_on_another_model(self):
        # 400 means our request is wrong; another model would reject it too.
        from unittest.mock import patch

        from app.services.solution.client import SolutionModelError

        client, tried = self._client({"main": SolutionModelError("400 INVALID_ARGUMENT"), "second": "reply"})
        with patch("app.services.solution.client.settings.SOLUTION_FALLBACK_MODELS", "second"):
            with self.assertRaises(SolutionModelError):
                client.solve("p")
        self.assertEqual(tried, ["main"])

    def test_when_every_model_is_spent_the_quota_error_reaches_the_student(self):
        from unittest.mock import patch

        from app.services.solution.client import SolutionQuotaError

        client, _ = self._client({"main": SolutionQuotaError("a"), "second": SolutionQuotaError("b")})
        with patch("app.services.solution.client.settings.SOLUTION_FALLBACK_MODELS", "second"):
            with self.assertRaises(SolutionQuotaError):
                client.solve("p")


class DeadlineTests(TestCase):
    """One deadline bounds every call, retry and fallback of a task."""

    def test_no_call_starts_once_the_budget_is_spent(self):
        import time

        from app.services.solution.client import SolutionClient, SolutionModelError

        client = SolutionClient.__new__(SolutionClient)
        client.model = "main"
        called = []
        client._client = type("C", (), {"models": type("M", (), {
            "generate_content": lambda self, **kw: called.append(kw)})()})()
        with self.assertRaises(SolutionModelError) as caught:
            client._call([], schema={}, temperature=0, thinking=None, deadline=time.monotonic() + 1)
        self.assertIn("time budget spent", str(caught.exception))
        self.assertEqual(called, [])

    def test_the_call_timeout_never_outlives_the_deadline(self):
        import time

        from app.services.solution.client import SolutionClient

        client = SolutionClient.__new__(SolutionClient)
        client.model = "main"
        seen = {}

        class _Response:
            text = "{}"
            model_version = "m"

        def generate_content(self, **kw):
            seen["timeout_ms"] = kw["config"].http_options.timeout
            return _Response()

        client._client = type("C", (), {"models": type("M", (), {"generate_content": generate_content})()})()
        client._call([], schema={}, temperature=0, thinking=None, deadline=time.monotonic() + 20)
        self.assertLessEqual(seen["timeout_ms"], 20_000)

    def test_every_round_of_a_bank_question_shares_one_deadline(self):
        client = FakeClient([solution("A"), solution("A")])
        explain(client)
        deadlines = {call["deadline"] for call in client.calls}
        self.assertEqual(len(deadlines), 1)
        self.assertIsNotNone(deadlines.pop())
