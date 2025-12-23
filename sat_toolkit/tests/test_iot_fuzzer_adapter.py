from django.test import TestCase


class TestIoTFuzzerAdapterModels(TestCase):
    def test_import_paths_and_basic_orm(self):
        # New adapter path
        from sat_toolkit.adapters.django.iot_fuzzer import models as new_models

        # Old shim `sat_toolkit.models.IoTFuzzer_Model` has been removed; new path is the source of truth.
        # `sat_toolkit.models` should NOT re-export Django models.
        import sat_toolkit.models as pkg_models
        assert not hasattr(pkg_models, "FuzzingCampaign")

        proto = new_models.ProtocolConfiguration.objects.create(protocol_type="can", settings={"baud_rate": 500000})
        campaign = new_models.FuzzingCampaign.objects.create(
            name="c1",
            description="d",
            status="idle",
            protocol_type="can",
            protocol_config={},
            generator_config={},
            monitoring_config={},
            total_cases=10,
            passed_cases=3,
            failed_cases=2,
        )
        group = new_models.TestGroup.objects.create(
            name="g1",
            description="gd",
            campaign=campaign,
            priority="normal",
            enabled=True,
            protocol_type="can",
        )
        case = new_models.TestCase.objects.create(
            name="tc1",
            description="tcd",
            priority="normal",
            enabled=True,
            group=group,
            protocol_config=proto,
            timeout_seconds=1.0,
            iterations=2,
        )
        field = new_models.FrameField.objects.create(
            test_case=case,
            field_name="f1",
            field_id="id1",
            field_type="hex",
            value="01",
            field_order=0,
        )
        rule = new_models.FuzzingRule.objects.create(
            test_case=case,
            rule_name="r1",
            description="rd",
            enabled=True,
            target_type="field",
            target_field=field,
            strategy="random",
            strategy_config={},
            iterations_per_rule=1,
            priority=50,
        )
        log = new_models.LiveLog.objects.create(
            campaign=campaign,
            level="info",
            category="test",
            source="unit-test",
            message="hello",
            extra_data={"x": 1},
        )

        # Basic method smoke checks
        assert campaign.can_start() is True
        assert campaign.get_progress_percentage() == 50.0
        assert group.get_completion_percentage() == 0
        assert isinstance(case.get_fuzzing_targets(), dict)
        assert rule._meta.verbose_name == "Fuzzing Rule"
        assert log.is_error() is False


