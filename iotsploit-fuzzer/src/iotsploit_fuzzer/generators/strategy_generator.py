"""Shared selected-case adapter; frame translation stays with the caller."""

class SelectedCaseGenerator:
    """Feed selected case mutations into the single protocol execution loop.

    A case with a batch saved in Management runs exactly those payloads;
    the engine generates only for cases without one.
    """
    def __init__(self, engine, cases, replay=None, saved=None):
        from iotsploit_fuzzer.core.fuzzing_engine import FuzzTestCase
        self.payloads = []
        self.case_settings = []
        self.on_case = None
        if replay is not None:
            self.payloads = [bytes.fromhex(replay["payload_hex"])]
            self.case_settings = [replay.get("config", {})]
        saved = saved or {}
        for case in cases:
            if str(case["id"]) in saved:
                payloads = [bytes.fromhex(p) for p in saved[str(case["id"])]]
            else:
                source = FuzzTestCase(str(case["id"]), case["name"], case["protocol_type"],
                                     case["frame_data"],
                                     case.get("frame_fields", []), case.get("fuzzing_rules", []),
                                     case.get("target_bits"))
                options = {"iterations": int(case.get("iterations", 100))}
                if "strategies" in case:
                    options["strategy_names"] = case["strategies"]
                mutations = engine.generate_mutations([source], **options)
                payloads = [m.mutated_data for batch in mutations.values() for m in batch]
            self.payloads.extend(payloads)
            self.case_settings.extend([case.get("protocol_config", {})] * len(payloads))
        if not self.payloads:
            raise ValueError("Selected cases generated no executable payloads")
        self.total = len(self.payloads)

    def seed_corpus(self):
        return self.payloads[:1]

    def generate(self, seeds, total):
        for payload, settings in zip(self.payloads[:total], self.case_settings[:total]):
            if self.on_case is not None:
                self.on_case(settings)
            yield payload

