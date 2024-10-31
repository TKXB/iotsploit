import unittest
import logging
from sat_toolkit.core.exploit_manager import ExploitPluginManager
from sat_toolkit.core.base_plugin import BasePlugin

class TestExploitPluginManager(unittest.TestCase):
    def setUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.plugin_manager = ExploitPluginManager()

    def test_syn_flood_plugin(self):
        # Test get_plugin
        plugin = self.plugin_manager.get_plugin("syn_flood_attack")
        self.assertIsNotNone(plugin)
        self.assertTrue(isinstance(plugin, BasePlugin))
        
        # Verify plugin attributes
        plugin_info = plugin.get_info()
        print("plugin_info", plugin_info)
        self.assertEqual(plugin_info['Name'], 'SYN Flood Attack')
        self.assertEqual(plugin_info['Platform'], ['linux', 'windows'])

    def test_list_plugin_info(self):
        # Test list_plugin_info
        plugin_info_dict = self.plugin_manager.list_plugin_info()
        print("plugin_info_dict", plugin_info_dict)
        
        # Verify SYN flood plugin info is present
        self.assertIn('syn_flood_attack', plugin_info_dict)
        
        # Verify specific plugin information
        syn_flood_info = plugin_info_dict['syn_flood_attack']
        self.assertEqual(syn_flood_info['Name'], 'SYN Flood Attack')
        self.assertEqual(syn_flood_info['Description'], 'Performs a SYN flood attack on a specified target.')
        self.assertEqual(syn_flood_info['License'], 'GPL')
        self.assertEqual(syn_flood_info['Platform'], ['linux', 'windows'])

if __name__ == '__main__':
    unittest.main()