import os

import django
from django.apps import apps
from django.test import SimpleTestCase


if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from iotsploit_django.tools.report_mgr import Report_Mgr


class TestReportTreeInitialization(SimpleTestCase):
    def setUp(self):
        self.manager = object.__new__(Report_Mgr)
        self.manager._Report_Mgr__report_toc_tree_list = []
        self.manager._Report_Mgr__report_detail_tree_list = []
        self.manager._Report_Mgr__report_test_result_tree_list = []

    def test_teststand_is_added_as_root(self):
        project = object()
        record = {"toc_level": 0, "test_stand": project}

        self.manager.record_TestStand_before_audit(record)

        nodes = record["active_teststand_list"]
        self.assertEqual(record["teststand_toc"], 0)
        self.assertIn("ts_before_teststand", record)
        self.assertEqual(nodes[2][0], {"test_project": project, "toc_level": 0, "status": "进行中"})
        self.assertIs(self.manager._Report_Mgr__report_toc_tree_list[0], nodes[0])
        self.assertIs(self.manager._Report_Mgr__report_detail_tree_list[0], nodes[1])
        self.assertIs(self.manager._Report_Mgr__report_test_result_tree_list[0], nodes[2])

    def test_testgroup_is_added_under_active_teststand(self):
        parent_nodes = (["", []], ["", []], [{}, []])
        project = object()
        record = {
            "toc_level": 1,
            "test_group": project,
            "active_teststand_list": parent_nodes,
        }

        self.manager.record_TestGroup_before_audit(record)

        nodes = record["active_testgroup_list"]
        for parent, node in zip(parent_nodes, nodes):
            self.assertIs(parent[1][0], node)
        self.assertEqual(nodes[2][0], {"test_project": project, "toc_level": 1, "status": "进行中"})

    def test_top_level_testcase_is_added_as_root(self):
        project = object()
        record = {"toc_level": 0, "test_case": project}

        self.manager.record_TestCase_before_audit(record)

        nodes = record["active_testcase_list"]
        self.assertIs(self.manager._Report_Mgr__report_toc_tree_list[0], nodes[0])
        self.assertIs(self.manager._Report_Mgr__report_detail_tree_list[0], nodes[1])
        self.assertIs(self.manager._Report_Mgr__report_test_result_tree_list[0], nodes[2])
