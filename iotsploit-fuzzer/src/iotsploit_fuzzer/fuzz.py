"""One-line fuzzing: name a function, say what it promises, go.

    python -m iotsploit_fuzzer.fuzz mypkg.parser:parse --raises ValueError

The full interface wants an adapter module, a dotted registry entry and a
seed file, which is the right shape for a target you intend to keep and far
too much for finding out whether a function you just wrote holds up. This
writes the adapter for you by reading the function's own signature, resolves
exception names against builtins and the function's own module, and takes
seeds as text on the command line.

It is a front end and nothing more. Everything it does can be done by hand,
and a target worth keeping should graduate into a pack -- see the README.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import os
import sys
from pathlib import Path
from typing import Any, Optional, Tuple

from .harnesses.parser_targets import (
    ParseTarget,
    json_input,
    register,
    temp_file,
    text_input,
)

#: How a payload is turned into the function's argument. The worker reads
#: these from the environment rather than a generated module, so there is
#: nothing to write to disk and nothing to clean up.
TARGET_ENV = "IOTSPLOIT_FUZZ_TARGET"
INPUT_ENV = "IOTSPLOIT_FUZZ_INPUT"

KINDS = ("bytes", "text", "json", "file")

_resolved: Optional[Any] = None


def _target() -> Any:
    global _resolved
    if _resolved is None:
        module, _, attribute = os.environ[TARGET_ENV].partition(":")
        _resolved = getattr(importlib.import_module(module), attribute)
    return _resolved


def auto(payload: bytes) -> Any:
    """The generated adapter, driven by the environment.

    One function rather than one per target, because the only thing that
    varies is how the payload becomes an argument.
    """
    kind = os.environ.get(INPUT_ENV, "bytes")
    function = _target()
    if kind == "bytes":
        return function(payload)
    if kind == "text":
        return function(text_input(payload))
    if kind == "json":
        return function(json_input(payload))
    suffix = kind[4:] or ".bin"          # "file.asc" -> ".asc"
    path = temp_file(payload, suffix)
    try:
        return function(path)
    finally:
        os.unlink(path)


# --------------------------------------------------------------------------
# Working out what to do, so the caller does not have to
# --------------------------------------------------------------------------


def infer_kind(function: Any) -> str:
    """Guess how this function wants its input, from its first parameter.

    A guess, and it says so when it is guessing: ``--input`` overrides.
    """
    try:
        first = next(iter(inspect.signature(function).parameters.values()))
    except (TypeError, ValueError, StopIteration):
        return "bytes"
    annotation = first.annotation
    name = first.name.lower()
    text = "" if annotation is inspect.Parameter.empty else str(annotation)

    lowered = text.lower()
    # Containers first: ``Dict[str, Any]`` contains "str", and checking for
    # text before the container would read every mapping as a string.
    if "dict" in lowered or "mapping" in lowered or "list" in lowered:
        return "json"
    if "bytes" in lowered:
        return "bytes"
    if "path" in lowered or name in ("path", "file", "filename", "filepath"):
        return "file"
    if "str" in lowered:
        return "text"
    return "bytes"


def resolve_exception(name: str, function: Any) -> str:
    """Turn ``ValueError`` or ``CanLogError`` into the dotted name the worker needs.

    Looked for in builtins first, then beside the function itself, which is
    where a parser's own error class almost always lives.
    """
    if ":" in name:
        return name
    if hasattr(__builtins__ if isinstance(__builtins__, dict) else __builtins__, "__getitem__"):
        pass
    import builtins

    if hasattr(builtins, name):
        return f"builtins:{name}"
    module = inspect.getmodule(function)
    if module is not None and hasattr(module, name):
        return f"{module.__name__}:{name}"
    raise SystemExit(
        f"cannot find an exception called {name!r} in builtins or in "
        f"{getattr(module, '__name__', '?')}. Give it as 'module:Name'."
    )


def load_target(spec: str) -> Tuple[Any, str]:
    """Import ``module:function``, or ``path/to/file.py:function``."""
    location, _, attribute = spec.rpartition(":")
    if not location or not attribute:
        raise SystemExit(f"expected 'module:function', got {spec!r}")
    if location.endswith(".py") or os.sep in location:
        path = Path(location).resolve()
        if not path.exists():
            raise SystemExit(f"no such file: {path}")
        sys.path.insert(0, str(path.parent))
        # The worker is a separate process and needs to find it too.
        os.environ["PYTHONPATH"] = os.pathsep.join(
            [str(path.parent), os.environ.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        location = path.stem
    try:
        function = getattr(importlib.import_module(location), attribute)
    except (ImportError, AttributeError) as error:
        raise SystemExit(f"cannot load {spec}: {error}") from None
    return function, f"{location}:{attribute}"


def preflight(target: ParseTarget) -> set:
    """Check the contract against the seeds before spending a campaign on it.

    A wrong ``--raises`` is the first mistake everyone makes, and it does not
    fail loudly -- it makes every input a violation, and every violation is
    replayed three times in a fresh process to confirm it. The run does not
    break, it just never finishes. Three calls here turn that into a sentence.

    Returns the exceptions the seeds raised that the contract does not cover,
    empty when at least one seed got through.
    """
    from .harnesses.parser_harness import ParserHarness
    from .analysis.outcome import ACCEPT, REJECT

    unexpected = set()
    with ParserHarness(target, repeats=1) as harness:
        for seed in target.seeds:
            outcome = harness.evaluate(seed)
            if outcome.kind in (ACCEPT, REJECT):
                return set()
            if outcome.exception:
                unexpected.add(outcome.exception)
    return unexpected


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m iotsploit_fuzzer.fuzz",
        description=__doc__.splitlines()[0],
        epilog=(
            "examples:\n"
            "  fuzz mypkg.config:load --raises ValueError --seed '{\"port\": 80}'\n"
            "  fuzz ./newfeature.py:parse_range --raises ValueError --seed 'bytes=0-9'\n"
            "  fuzz mypkg.log:scan --raises LogError --seed @capture.asc --input file.asc\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("target", help="module:function, or path/to/file.py:function")
    parser.add_argument(
        "--raises", default="",
        help="comma-separated exceptions the function promises, e.g. 'ValueError'. "
             "Empty means it promises never to raise -- and if that is not true, "
             "every input will look like a defect",
    )
    parser.add_argument(
        "--seed", action="append", default=[], metavar="TEXT|@FILE",
        help="a valid input to mutate from, literal or @file. Repeatable. "
             "Without one the fuzzer explores the first few bytes and stops",
    )
    parser.add_argument("--input", choices=KINDS, help="override the guessed input kind")
    parser.add_argument("-n", "--iterations", type=int, default=2000)
    parser.add_argument("--seconds", type=float, default=5.0, help="budget for one call")
    parser.add_argument("--keep", metavar="DIR", help="keep the corpus here")
    parser.add_argument("--radamsa", action="store_true")
    args = parser.parse_args(argv)

    function, dotted = load_target(args.target)
    kind = args.input or infer_kind(function)
    declared = tuple(
        resolve_exception(n.strip(), function) for n in args.raises.split(",") if n.strip()
    )
    seeds = tuple(
        Path(s[1:]).read_bytes() if s.startswith("@") else s.encode()
        for s in args.seed
    ) or (b"",)

    os.environ[TARGET_ENV] = dotted
    os.environ[INPUT_ENV] = kind

    print(f"target   {dotted}")
    print(f"input    {kind}{' (guessed)' if not args.input else ''}")
    print(f"promises {', '.join(declared) or 'never raises'}")
    print(f"seeds    {len(seeds)}" + ("  -- none given, findings will be shallow" if seeds == (b"",) else ""))
    print()

    # Driven directly rather than through the campaign CLI, which would load a
    # target pack this has no use for -- and, for a caller fuzzing their own
    # code, might not even be able to import.
    import tempfile

    from .core.parser_campaign import describe, run
    from .generators.radamsa_generator import RadamsaGenerator

    target = register(ParseTarget(
        name=dotted.replace(":", "."),
        adapter="iotsploit_fuzzer.fuzz:auto",
        declared=declared,
        seeds=seeds,
        budget_seconds=args.seconds,
    ))
    unexpected = preflight(target)
    if unexpected:
        print("Stopping: the seeds already break the contract you gave.")
        print("Every one of them raised something --raises does not cover:\n")
        for exception in sorted(unexpected):
            print(f"    {exception}")
        print(
            "\nEither the function does not promise what you said, or these are\n"
            "its declared errors. Re-run with:\n\n"
            f"    --raises {','.join(sorted(e.split(':')[-1] for e in unexpected))}\n\n"
            "Left as it is, every input looks like a defect and each one is\n"
            "replayed three times to confirm it, which takes all night."
        )
        return 2

    root = args.keep or tempfile.mkdtemp(prefix="fuzz_")
    report = run(
        target,
        iterations=args.iterations,
        root=root,
        rebaseline=True,
        radamsa=RadamsaGenerator(seed=0) if args.radamsa else None,
    )
    describe(target.name, report)
    if not args.keep:
        print(f"\ncorpus (temporary): {root}")
    return 1 if report["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
