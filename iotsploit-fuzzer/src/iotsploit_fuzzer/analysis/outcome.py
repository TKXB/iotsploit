"""What a parse target did, in a form two campaigns a month apart can compare.

A crash count answers "did anything break tonight" and nothing else. What
keeps paying out is the *error boundary*: the frontier between the inputs a
parser accepts and the ones it rejects, which is the parser's real contract as
opposed to the one its docstring claims. Recording the boundary means a
refactor that quietly narrows what a parser accepts shows up as a diff.

That only works if the recorded form is stable. A raw exception message
carries offsets, hex, paths and quoted input, so comparing messages would
report thousands of boundary movements every time the corpus changed. Every
field of a :class:`Outcome` signature is normalised to survive that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict

#: Bumped whenever classification or normalisation changes. Part of every
#: target's fingerprint, because a signature computed by one version of this
#: module is not comparable with one computed by another -- and a ledger
#: compared across that line reports every entry as a boundary movement.
OUTCOME_VERSION = 8

#: The parser returned a value.
ACCEPT = "accept"
#: The parser raised an exception its contract declares.
REJECT = "reject"
#: Anything else escaped -- an undeclared exception, or a broken invariant.
VIOLATE = "violate"
#: The parse did not finish inside its wall-clock budget.
TIMEOUT = "timeout"
#: A resource limit stopped the worker: memory, output size, or CPU.
LIMIT = "limit"
#: The adapter could not build an input out of this payload. Not a result.
SKIP = "skip"

#: Kinds that fail a nightly run and are worth a human's attention. A parser
#: that hangs or exhausts memory on a bounded input is as broken as one that
#: raises something undeclared -- and worse, because no ``except`` catches it.
FINDING_KINDS = (VIOLATE, TIMEOUT, LIMIT)

_MAX_REASON = 80

#: Words of the message kept. An error names its invariant first and echoes
#: the offending input afterwards, so a bounded prefix is the part that says
#: *which* rejection this is.
_MAX_WORDS = 8

#: Characters of the message scrubbed at all. Only the first few words survive,
#: so reading further buys nothing -- and a parser that quotes its input puts
#: the whole payload in the message, which is how a 79 KB exception took 36
#: seconds to normalise and was reported as the target timing out.
_MAX_SCRUBBED = 2000

#: Characters kept from the end of a long message, so the clause after the
#: quoted input survives the clip.
_MAX_TAIL = 200

# Applied in this order: paths first, then the quoted span, then the numbers
# that would otherwise survive inside what is left.
#
# The quote rule is deliberately greedy -- first quote character to last. A
# message that quotes the fuzzer's own input cannot be parsed for balanced
# pairs, because the input contains quotes too, and the non-greedy reading
# scrubs the wrong span: it removes ``'a'`` from ``'a'b'`` and leaves the
# *message's* own words exposed to the payload's variety. Greedy over-merges
# at worst, and over-merging costs resolution while under-merging costs the
# whole corpus.
_SCRUB = (
    # Anchored on the separator rather than around it. The obvious spelling,
    # ``[\w./\\-]*[/\\][\w./\\-]*``, lets the leading class consume a run that
    # contains no separator at all and then backtrack one character at a time
    # looking for one, which is quadratic in the length of the run.
    (re.compile(r"[\w.-]*(?:[/\\][\w.-]*)+"), " "),
    (re.compile(r"['\"].*['\"]", re.DOTALL), " "),
    (re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-fx]{2,}\b"), " "),
    (re.compile(r"\b\d[\d_.]*\b"), " "),
)

_WORD = re.compile(r"[a-z_]{2,}")


def normalize_reason(message: str, payload: bytes = b"") -> str:
    """Reduce an exception message to a reason code two runs can compare.

    Scrubbing the varying parts is not enough on its own. A message like
    ``Invalid range format: '<payload>'. Expected format: 'start-end'`` quotes
    the fuzzer's own input, and a payload that itself contains an apostrophe
    shifts the pairing so that the wrong span is removed -- which turns one
    rejection into hundreds of distinct "reasons" and fills the corpus with
    inputs that all prove the same point.

    Three passes, in order of how much they assume. Scrub the parts that are
    recognisably variable; drop any word that appears in the payload, because
    a reason code that echoes the input is not a reason code; keep only the
    first few whole words, since an error names its invariant before it
    quotes what violated it.
    """
    text = _clip(message).strip().lower()
    for pattern, replacement in _SCRUB:
        text = pattern.sub(replacement, text)
    echoed = payload.decode("latin-1").lower()
    words = _keep(text, echoed)
    if not words:
        # ``str(KeyError("x"))`` is ``"'x'"`` -- the whole message is quoted,
        # so scrubbing leaves nothing. Fall back to the raw text: dropping the
        # words the payload echoes is what keeps it stable, not the quoting.
        words = _keep(_clip(message).lower(), echoed)
    return " ".join(words[:_MAX_WORDS])[:_MAX_REASON]


def _clip(message: str) -> str:
    """Head and tail, never the middle.

    An error that quotes its input puts the payload between the clause naming
    the invariant and the clause naming what was expected. Taking only a
    prefix drops the second one, which splits one rejection into a short-input
    signature and a long-input signature.
    """
    raw = message or ""
    if len(raw) <= _MAX_SCRUBBED:
        return raw
    return raw[: _MAX_SCRUBBED - _MAX_TAIL] + " " + raw[-_MAX_TAIL:]


def _keep(text: str, echoed: str) -> list:
    """Whole words that did not come from the input that provoked them.

    Length is not a reason to keep one. Short words were exempted so that an
    ordinary "is" or "be" could not be dropped by a payload that happened to
    contain it -- but a two-letter fragment of the payload is exactly what
    leaks through, and ``invalid host or cidr ss ss`` became two hundred
    distinct reasons for one rejection.

    Both mistakes are possible and they are not equally bad: dropping a real
    word merges two reasons, keeping a payload fragment splits one into
    hundreds. A bounded corpus prefers the merge.
    """
    return [w for w in _WORD.findall(text) if w not in echoed]


#: Fields of a returned record that reach the signature, in declaration order
#: rather than alphabetical: an author puts the load-bearing field first, and
#: sorting dropped ``LogReadStats.unparsable_lines`` -- the one its own
#: docstring calls "the number that matters". Capped so that a wide dataclass
#: cannot make every result unique.
_MAX_FIELDS = 6


def _bucket(size: int) -> str:
    """Size as a magnitude, so a length does not become part of the identity."""
    if size < 2:
        return str(size)
    if size < 10:
        return "few"
    if size < 100:
        return "tens"
    if size < 1000:
        return "hundreds"
    return "many"


def describe_shape(value: Any, _depth: int = 0) -> str:
    """The shape of a returned value, bucketed so signatures stay bounded.

    Two accepted inputs that produce a 3-frame and a 4-frame result are the
    same region of the boundary; one that produces an empty result is not.
    """
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        # Bucketed like a length, and for the same reason. A parse that
        # returns 3 frames and one that returns 4 are the same region; one
        # that returns none is a different one, and without this every
        # dataclass result collapses to a single signature with no boundary
        # in it at all.
        return f"{'-' if value < 0 else ''}num[{_bucket(abs(int(value)))}]"
    if isinstance(value, str):
        return f"str[{_bucket(len(value))}]"
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"bytes[{_bucket(len(bytes(value)))}]"
    if isinstance(value, dict):
        inner = _members(value.values(), _depth)
        return f"dict[{_bucket(len(value))}]{inner}"
    if isinstance(value, (list, tuple, set, frozenset)):
        inner = _members(value, _depth)
        return f"{type(value).__name__}[{_bucket(len(value))}]{inner}"
    fields = getattr(value, "__dataclass_fields__", None)
    if fields is not None and _depth < 1:
        described = ",".join(
            f"{name}={describe_shape(getattr(value, name, None), _depth + 1)}"
            for name in list(fields)[:_MAX_FIELDS]
        )
        return f"{type(value).__name__}({described})"
    return type(value).__name__


def _members(values: Any, depth: int) -> str:
    """The distinct shapes inside a container, at most one level deep."""
    if depth >= 1:
        return ""
    shapes = sorted({describe_shape(item, depth + 1) for item in list(values)[:32]})
    return "<" + ",".join(shapes[:3]) + ">" if shapes else ""


@dataclass(frozen=True)
class Outcome:
    """One parse, classified.

    ``signature`` is what the ledger stores and diffs. ``detail`` is for the
    human reading the report and is deliberately *not* part of the signature:
    it carries the raw message and the source location, both of which move.
    """

    kind: str
    exception: str = ""
    reason: str = ""
    shape: str = ""
    metamorphic: str = ""
    detail: str = ""
    site: str = ""

    @property
    def signature(self) -> str:
        return "|".join(
            (self.kind, self.exception, self.reason, self.shape, self.metamorphic)
        )

    @property
    def is_finding(self) -> bool:
        return self.kind in FINDING_KINDS

    def to_dict(self) -> Dict[str, str]:
        return {
            "kind": self.kind,
            "exception": self.exception,
            "reason": self.reason,
            "shape": self.shape,
            "metamorphic": self.metamorphic,
            "detail": self.detail,
            "site": self.site,
        }

    @classmethod
    def from_signature(cls, signature: str, detail: str = "", site: str = "") -> "Outcome":
        """Rebuild from the signature the harness put on a HarnessResult.

        Lossy by design -- ``detail`` and ``site`` do not survive, and are not
        supposed to: they are never compared.
        """
        parts = (signature or "").split("|")
        parts += [""] * (5 - len(parts))
        return cls(
            kind=parts[0] or VIOLATE, exception=parts[1], reason=parts[2],
            shape=parts[3], metamorphic=parts[4], detail=detail, site=site,
        )

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Outcome":
        return cls(
            kind=str(raw.get("kind", VIOLATE)),
            exception=str(raw.get("exception", "")),
            reason=str(raw.get("reason", "")),
            shape=str(raw.get("shape", "")),
            metamorphic=str(raw.get("metamorphic", "")),
            detail=str(raw.get("detail", "")),
            site=str(raw.get("site", "")),
        )
