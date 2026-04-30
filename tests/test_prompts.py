"""Tests for prompts.py — all prompt templates are valid."""

import pytest


class TestPromptConstants:
    def test_extract_prompt_has_placeholder(self):
        from prompts import EXTRACT_PROMPT
        assert "{subject}" in EXTRACT_PROMPT

    def test_evaluate_prompt_has_placeholders(self):
        from prompts import EVALUATE_PROMPT
        assert "{subject}" in EVALUATE_PROMPT
        assert "{exam_context}" in EVALUATE_PROMPT
        assert "__EXTRACTED_TEXT__" in EVALUATE_PROMPT

    def test_hint_prompt_has_placeholders(self):
        from prompts import HINT_PROMPT
        assert "{subject}" in HINT_PROMPT
        assert "{exam_context}" in HINT_PROMPT

    def test_practice_prompt_has_placeholders(self):
        from prompts import PRACTICE_PROMPT
        assert "{difficulty}" in PRACTICE_PROMPT
        assert "{subject}" in PRACTICE_PROMPT
        assert "{exam}" in PRACTICE_PROMPT
        assert "{topic}" in PRACTICE_PROMPT
        assert "{exam_specific}" in PRACTICE_PROMPT

    def test_explain_prompt_has_placeholders(self):
        from prompts import EXPLAIN_PROMPT
        assert "{subject}" in EXPLAIN_PROMPT
        assert "{exam}" in EXPLAIN_PROMPT
        assert "{topic}" in EXPLAIN_PROMPT

    def test_debate_prompt_has_placeholders(self):
        from prompts import DEBATE_PROMPT
        assert "{subject}" in DEBATE_PROMPT
        assert "{question_text}" in DEBATE_PROMPT
        assert "{student_message}" in DEBATE_PROMPT

    def test_wow_extract_prompt_has_placeholders(self):
        from prompts import WOW_EXTRACT_PROMPT
        assert "{subject}" in WOW_EXTRACT_PROMPT
        assert "{topic}" in WOW_EXTRACT_PROMPT
        assert "{mentor_reply}" in WOW_EXTRACT_PROMPT
        assert "{student_message}" in WOW_EXTRACT_PROMPT

    def test_exam_contexts_dict(self):
        from prompts import EXAM_CONTEXTS
        assert "jee_main" in EXAM_CONTEXTS
        assert "jee_advanced" in EXAM_CONTEXTS
        assert "general" in EXAM_CONTEXTS

    def test_practice_exam_reqs_dict(self):
        from prompts import PRACTICE_EXAM_REQS
        assert "jee_main" in PRACTICE_EXAM_REQS
        assert "general" in PRACTICE_EXAM_REQS


class TestPromptFormatting:
    """Verify prompts can be .format()'d without KeyError."""

    def test_extract_prompt_formats(self):
        from prompts import EXTRACT_PROMPT
        result = EXTRACT_PROMPT.format(subject="maths")
        assert "maths" in result

    def test_evaluate_prompt_formats(self):
        from prompts import EVALUATE_PROMPT
        result = EVALUATE_PROMPT.format(subject="physics", exam_context="JEE Main")
        assert "physics" in result
        # __EXTRACTED_TEXT__ stays (replaced with .replace() not .format())
        assert "__EXTRACTED_TEXT__" in result

    def test_hint_prompt_formats(self):
        from prompts import HINT_PROMPT
        result = HINT_PROMPT.format(subject="chemistry", exam_context="Board exam")
        assert "chemistry" in result

    def test_practice_prompt_formats(self):
        from prompts import PRACTICE_PROMPT
        result = PRACTICE_PROMPT.format(
            difficulty="hard", subject="maths", exam="jee_advanced",
            topic="calculus", exam_specific="Multi-concept problems"
        )
        assert "hard" in result
        assert "calculus" in result

    def test_explain_prompt_formats(self):
        from prompts import EXPLAIN_PROMPT
        result = EXPLAIN_PROMPT.format(subject="physics", exam="jee_main", topic="optics")
        assert "optics" in result

    def test_debate_prompt_formats(self):
        from prompts import DEBATE_PROMPT
        result = DEBATE_PROMPT.format(
            subject="maths", exam="general", question_text="x+1=2",
            topic="algebra", correctness=3, what_went_right="good",
            where_it_broke="step 2", missing_concept="signs",
            history_text="", student_message="I tried adding",
        )
        assert "I tried adding" in result

    def test_wow_extract_prompt_formats(self):
        from prompts import WOW_EXTRACT_PROMPT
        result = WOW_EXTRACT_PROMPT.format(
            subject="maths", topic="calculus",
            mentor_reply="Think about limits", student_message="Oh I see!"
        )
        assert "limits" in result
