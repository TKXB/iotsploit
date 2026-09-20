"""An outcome signature must mean the same thing in two campaigns a month apart.

Everything the boundary ledger does rests on this. If a signature moves for
any reason other than the parser's behaviour changing, every nightly report
fills with movements nobody caused, and the report stops being read -- which
is the failure mode this whole loop is designed against.
"""

from __future__ import annotations

import pytest

from iotsploit_fuzzer.analysis.outcome import (
    ACCEPT,
    REJECT,
    VIOLATE,
    Outcome,
    describe_shape,
    normalize_reason,
)

pytestmark = pytest.mark.unit


class TestNormalizeReason:
    @pytest.mark.parametrize(
        ("first", "second"),
        [
            # The same rejection, reached by two different inputs.
            ("UDS negative response truncated: 7f10", "UDS negative response truncated: 22ab04"),
            ("ARXML file is 900 bytes; the limit is 512", "ARXML file is 12 bytes; the limit is 512"),
            ("cannot read file /tmp/a/x.arxml: denied", "cannot read file /var/b/y.arxml: denied"),
            ("frame id 0x1ff is out of range", "frame id 0x7 is out of range"),
        ],
    )
    def test_inputs_that_differ_only_in_their_data_share_a_reason(self, first, second):
        assert normalize_reason(first) == normalize_reason(second)
        assert normalize_reason(first) != ""

    def test_different_rejections_keep_different_reasons(self):
        empty = normalize_reason("UDS service 0x22: empty response")
        truncated = normalize_reason("UDS negative response truncated: 7f10")

        assert empty != truncated

    def test_a_message_quoting_the_payload_does_not_inherit_its_variety(self):
        """The defect that made one rejection look like hundreds.

        ``Invalid range format: '<payload>'`` echoes the input, and a payload
        containing an apostrophe shifts the quote pairing so the wrong span is
        scrubbed. Dropping words the payload contains is what closes it.
        """
        plain = normalize_reason(
            "Invalid range format: '1-2-3'. Expected format: 'start-end'", b"1-2-3"
        )
        quoted = normalize_reason(
            "Invalid range format: 'a'b'. Expected format: 'start-end'", b"a'b"
        )

        assert plain == quoted

    def test_a_fully_quoted_message_still_yields_a_reason(self):
        """``str(KeyError('x'))`` is ``\"'x'\"`` -- scrubbing alone leaves nothing."""
        assert normalize_reason("'no such signal in frame'", b"\x00") != ""

    def test_reason_is_bounded(self):
        assert len(normalize_reason("word " * 500)) <= 80


class TestDescribeShape:
    def test_length_is_bucketed_so_a_count_is_not_an_identity(self):
        assert describe_shape([1] * 12) == describe_shape([1] * 40)
        assert describe_shape([1] * 12) != describe_shape([1] * 2)

    def test_empty_and_populated_results_are_different_regions(self):
        assert describe_shape([]) != describe_shape([1])

    def test_nesting_stops_at_one_level(self):
        """Unbounded recursion into a parsed document would put the document
        itself in the signature."""
        shape = describe_shape([{"a": [{"b": [1, 2]}]}])

        assert shape.count("<") <= 2


class TestSignature:
    def test_signature_survives_the_harness_seam(self):
        original = Outcome(kind=REJECT, exception="CanLogError", reason="bad header")

        assert Outcome.from_signature(original.signature).signature == original.signature

    def test_detail_and_site_are_not_compared(self):
        """Both move under an edit that changes no behaviour."""
        first = Outcome(kind=ACCEPT, shape="list[few]", detail="at offset 12", site="a.py:1")
        second = Outcome(kind=ACCEPT, shape="list[few]", detail="at offset 900", site="a.py:8")

        assert first.signature == second.signature

    @pytest.mark.parametrize(
        ("kind", "expected"),
        [(ACCEPT, False), (REJECT, False), (VIOLATE, True), ("timeout", True), ("limit", True)],
    )
    def test_only_the_three_out_of_contract_kinds_are_findings(self, kind, expected):
        assert Outcome(kind=kind).is_finding is expected
