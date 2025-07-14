import logging
import threading
import json
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

class IoTFuzzerService:
    """
    IoT Fuzzer Service - Business logic layer for test management and configuration
    Pure Django service layer without direct fuzzer dependencies
    """
    
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        """Get singleton instance of IoTFuzzerService"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        """Initialize the IoT Fuzzer Service"""
        if IoTFuzzerService._instance is not None:
            raise Exception("This class is a singleton!")
        
        self.protocol_configs: Dict[str, Dict[str, Any]] = {}
        self.generator_configs: Dict[str, Dict[str, Any]] = {}
        self.test_groups: Dict[str, Dict[str, Any]] = {}
        self.test_cases: Dict[str, Dict[str, Any]] = {}
        self.templates: Dict[str, Dict[str, Any]] = {}
        
        # Initialize with default templates
        self._initialize_default_templates()
        
        logger.info("IoT Fuzzer Service initialized")
    
    # Test Group Management
    def get_test_groups(self, campaign_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get test groups with progress information
        
        Args:
            campaign_id: Optional campaign ID to filter groups
            
        Returns:
            List[Dict]: List of test groups with metadata
        """
        try:
            groups = []
            
            for group_id, group_data in self.test_groups.items():
                if campaign_id and group_data.get('campaign_id') != campaign_id:
                    continue
                
                # Calculate group statistics
                group_stats = self._calculate_group_statistics(group_id)
                
                group_info = {
                    'id': group_id,
                    'name': group_data.get('name', 'Unnamed Group'),
                    'description': group_data.get('description', ''),
                    'protocol_type': group_data.get('protocol_type', 'unknown'),
                    'mutation_strategy': group_data.get('mutation_strategy', 'random'),
                    'priority': group_data.get('priority', 'normal'),
                    'enabled': group_data.get('enabled', True),
                    'created_at': group_data.get('created_at', ''),
                    'total_cases': group_stats['total_cases'],
                    'completed_cases': group_stats['completed_cases'],
                    'failed_cases': group_stats['failed_cases'],
                    'progress_percentage': group_stats['progress_percentage']
                }
                
                groups.append(group_info)
            
            return groups
            
        except Exception as e:
            logger.error(f"Error getting test groups: {str(e)}")
            raise
    
    def create_test_group(self, group_config: Dict[str, Any]) -> str:
        """
        Create a new test group
        
        Args:
            group_config: Group configuration
            
        Returns:
            str: Group ID
        """
        try:
            # Validate group configuration
            self._validate_group_config(group_config)
            
            # Generate group ID
            group_id = str(uuid.uuid4())
            
            # Create group data
            group_data = {
                'id': group_id,
                'name': group_config.get('name', 'Unnamed Group'),
                'description': group_config.get('description', ''),
                'protocol_type': group_config.get('protocol_type', 'unknown'),
                'mutation_strategy': group_config.get('mutation_strategy', 'random'),
                'priority': group_config.get('priority', 'normal'),
                'enabled': group_config.get('enabled', True),
                'created_at': datetime.now().isoformat(),
                'campaign_id': group_config.get('campaign_id'),
                'test_cases': []
            }
            
            # Store group
            self.test_groups[group_id] = group_data
            
            logger.info(f"Test group {group_id} created successfully")
            return group_id
            
        except Exception as e:
            logger.error(f"Error creating test group: {str(e)}")
            raise
    
    def update_test_group(self, group_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update test group properties
        
        Args:
            group_id: Group ID to update
            updates: Update data
            
        Returns:
            Dict: Updated group data
        """
        try:
            if group_id not in self.test_groups:
                raise Exception(f"Test group {group_id} not found")
            
            group_data = self.test_groups[group_id]
            
            # Update allowed fields
            allowed_fields = ['name', 'description', 'priority', 'enabled', 'mutation_strategy']
            for field in allowed_fields:
                if field in updates:
                    group_data[field] = updates[field]
            
            group_data['updated_at'] = datetime.now().isoformat()
            
            logger.info(f"Test group {group_id} updated successfully")
            return group_data
            
        except Exception as e:
            logger.error(f"Error updating test group {group_id}: {str(e)}")
            raise
    
    def delete_test_group(self, group_id: str) -> bool:
        """
        Delete test group and associated test cases
        
        Args:
            group_id: Group ID to delete
            
        Returns:
            bool: Success status
        """
        try:
            if group_id not in self.test_groups:
                raise Exception(f"Test group {group_id} not found")
            
            # Delete associated test cases
            group_data = self.test_groups[group_id]
            for case_id in group_data.get('test_cases', []):
                if case_id in self.test_cases:
                    del self.test_cases[case_id]
            
            # Delete group
            del self.test_groups[group_id]
            
            logger.info(f"Test group {group_id} deleted successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting test group {group_id}: {str(e)}")
            raise
    
    # Test Case Management
    def get_test_cases(self, group_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get test cases with group assignment
        
        Args:
            group_id: Optional group ID to filter cases
            
        Returns:
            List[Dict]: List of test cases
        """
        try:
            cases = []
            
            for case_id, case_data in self.test_cases.items():
                if group_id and case_data.get('group_id') != group_id:
                    continue
                
                case_info = {
                    'id': case_id,
                    'name': case_data.get('name', 'Unnamed Case'),
                    'description': case_data.get('description', ''),
                    'group_id': case_data.get('group_id'),
                    'protocol_frame': case_data.get('protocol_frame', {}),
                    'expected_response': case_data.get('expected_response'),
                    'timeout_seconds': case_data.get('timeout_seconds', 1.0),
                    'priority': case_data.get('priority', 'normal'),
                    'enabled': case_data.get('enabled', True),
                    'execution_count': case_data.get('execution_count', 0),
                    'last_executed': case_data.get('last_executed'),
                    'last_result': case_data.get('last_result'),
                    'created_at': case_data.get('created_at', '')
                }
                
                cases.append(case_info)
            
            return cases
            
        except Exception as e:
            logger.error(f"Error getting test cases: {str(e)}")
            raise
    
    def create_test_case(self, case_config: Dict[str, Any]) -> str:
        """
        Create a new test case
        
        Args:
            case_config: Test case configuration
            
        Returns:
            str: Case ID
        """
        try:
            # Validate case configuration
            self._validate_case_config(case_config)
            
            # Generate case ID
            case_id = str(uuid.uuid4())
            
            # Create case data
            case_data = {
                'id': case_id,
                'name': case_config.get('name', 'Unnamed Case'),
                'description': case_config.get('description', ''),
                'group_id': case_config.get('group_id'),
                'protocol_frame': case_config.get('protocol_frame', {}),
                'expected_response': case_config.get('expected_response'),
                'timeout_seconds': case_config.get('timeout_seconds', 1.0),
                'priority': case_config.get('priority', 'normal'),
                'enabled': case_config.get('enabled', True),
                'execution_count': 0,
                'last_executed': None,
                'last_result': None,
                'created_at': datetime.now().isoformat()
            }
            
            # Store case
            self.test_cases[case_id] = case_data
            
            # Add to group
            group_id = case_config.get('group_id')
            if group_id and group_id in self.test_groups:
                self.test_groups[group_id]['test_cases'].append(case_id)
            
            logger.info(f"Test case {case_id} created successfully")
            return case_id
            
        except Exception as e:
            logger.error(f"Error creating test case: {str(e)}")
            raise
    
    def update_test_case(self, case_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update test case properties
        
        Args:
            case_id: Case ID to update
            updates: Update data
            
        Returns:
            Dict: Updated case data
        """
        try:
            if case_id not in self.test_cases:
                raise Exception(f"Test case {case_id} not found")
            
            case_data = self.test_cases[case_id]
            
            # Update allowed fields
            allowed_fields = ['name', 'description', 'protocol_frame', 'expected_response', 
                            'timeout_seconds', 'priority', 'enabled']
            for field in allowed_fields:
                if field in updates:
                    case_data[field] = updates[field]
            
            case_data['updated_at'] = datetime.now().isoformat()
            
            logger.info(f"Test case {case_id} updated successfully")
            return case_data
            
        except Exception as e:
            logger.error(f"Error updating test case {case_id}: {str(e)}")
            raise
    
    def delete_test_case(self, case_id: str) -> bool:
        """
        Delete test case
        
        Args:
            case_id: Case ID to delete
            
        Returns:
            bool: Success status
        """
        try:
            if case_id not in self.test_cases:
                raise Exception(f"Test case {case_id} not found")
            
            # Remove from group
            case_data = self.test_cases[case_id]
            group_id = case_data.get('group_id')
            if group_id and group_id in self.test_groups:
                group_cases = self.test_groups[group_id]['test_cases']
                if case_id in group_cases:
                    group_cases.remove(case_id)
            
            # Delete case
            del self.test_cases[case_id]
            
            logger.info(f"Test case {case_id} deleted successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting test case {case_id}: {str(e)}")
            raise
    
    # Configuration Management
    def get_protocol_config(self, config_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get protocol configuration
        
        Args:
            config_id: Optional config ID
            
        Returns:
            Dict: Protocol configuration
        """
        try:
            if config_id:
                if config_id not in self.protocol_configs:
                    raise Exception(f"Protocol config {config_id} not found")
                return self.protocol_configs[config_id]
            else:
                return list(self.protocol_configs.values())
                
        except Exception as e:
            logger.error(f"Error getting protocol config: {str(e)}")
            raise
    
    def save_protocol_config(self, config_data: Dict[str, Any]) -> str:
        """
        Save protocol configuration
        
        Args:
            config_data: Configuration data
            
        Returns:
            str: Configuration ID
        """
        try:
            # Validate configuration
            self._validate_protocol_config(config_data)
            
            # Generate config ID
            config_id = str(uuid.uuid4())
            
            # Save configuration
            config_entry = {
                'id': config_id,
                'name': config_data.get('name', 'Unnamed Config'),
                'protocol_type': config_data.get('protocol_type', 'unknown'),
                'configuration': config_data,
                'created_at': datetime.now().isoformat()
            }
            
            self.protocol_configs[config_id] = config_entry
            
            logger.info(f"Protocol config {config_id} saved successfully")
            return config_id
            
        except Exception as e:
            logger.error(f"Error saving protocol config: {str(e)}")
            raise
    
    # Template Management
    def get_templates(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get configuration templates
        
        Args:
            category: Optional category filter
            
        Returns:
            List[Dict]: List of templates
        """
        try:
            templates = []
            
            for template_id, template_data in self.templates.items():
                if category and template_data.get('category') != category:
                    continue
                
                templates.append(template_data)
            
            return templates
            
        except Exception as e:
            logger.error(f"Error getting templates: {str(e)}")
            raise
    
    def load_template(self, template_id: str) -> Dict[str, Any]:
        """
        Load template configuration
        
        Args:
            template_id: Template ID
            
        Returns:
            Dict: Template configuration
        """
        try:
            if template_id not in self.templates:
                raise Exception(f"Template {template_id} not found")
            
            template_data = self.templates[template_id]
            
            # Increment usage count
            template_data['usage_count'] = template_data.get('usage_count', 0) + 1
            
            return template_data['configuration']
            
        except Exception as e:
            logger.error(f"Error loading template {template_id}: {str(e)}")
            raise
    
    def save_template(self, template_data: Dict[str, Any]) -> str:
        """
        Save configuration as template
        
        Args:
            template_data: Template data
            
        Returns:
            str: Template ID
        """
        try:
            # Generate template ID
            template_id = str(uuid.uuid4())
            
            # Save template
            template_entry = {
                'id': template_id,
                'name': template_data.get('name', 'Unnamed Template'),
                'description': template_data.get('description', ''),
                'category': template_data.get('category', 'custom'),
                'configuration': template_data.get('configuration', {}),
                'created_at': datetime.now().isoformat(),
                'usage_count': 0
            }
            
            self.templates[template_id] = template_entry
            
            logger.info(f"Template {template_id} saved successfully")
            return template_id
            
        except Exception as e:
            logger.error(f"Error saving template: {str(e)}")
            raise
    
    # Private helper methods
    def _initialize_default_templates(self):
        """Initialize default configuration templates"""
        default_templates = {
            'automotive_can': {
                'id': 'automotive_can',
                'name': 'Automotive CAN',
                'description': 'Standard automotive CAN protocol template',
                'category': 'automotive',
                'configuration': {
                    'protocol_type': 'can',
                    'protocol_config': {
                        'interface': 'can0',
                        'bitrate': 500000,
                        'extended_id': True
                    },
                    'generator_config': {
                        'type': 'radamsa',
                        'mutation_rate': 0.1,
                        'seed_corpus': []
                    }
                },
                'created_at': datetime.now().isoformat(),
                'usage_count': 0
            },
            'iot_uart': {
                'id': 'iot_uart',
                'name': 'IoT UART',
                'description': 'Standard IoT UART protocol template',
                'category': 'iot',
                'configuration': {
                    'protocol_type': 'uart',
                    'protocol_config': {
                        'port': '/dev/ttyUSB0',
                        'baud_rate': 115200,
                        'data_bits': 8,
                        'stop_bits': 1,
                        'parity': 'none'
                    },
                    'generator_config': {
                        'type': 'random',
                        'min_length': 1,
                        'max_length': 256
                    }
                },
                'created_at': datetime.now().isoformat(),
                'usage_count': 0
            }
        }
        
        self.templates.update(default_templates)
    
    def _validate_group_config(self, config: Dict[str, Any]) -> None:
        """Validate test group configuration"""
        required_fields = ['name', 'protocol_type']
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required field: {field}")
    
    def _validate_case_config(self, config: Dict[str, Any]) -> None:
        """Validate test case configuration"""
        required_fields = ['name', 'group_id', 'protocol_frame']
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required field: {field}")
    
    def _validate_protocol_config(self, config: Dict[str, Any]) -> None:
        """Validate protocol configuration"""
        required_fields = ['protocol_type']
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required field: {field}")
    
    def _calculate_group_statistics(self, group_id: str) -> Dict[str, Any]:
        """Calculate statistics for a test group"""
        group_data = self.test_groups.get(group_id, {})
        test_cases = group_data.get('test_cases', [])
        
        total_cases = len(test_cases)
        completed_cases = 0
        failed_cases = 0
        
        for case_id in test_cases:
            if case_id in self.test_cases:
                case_data = self.test_cases[case_id]
                if case_data.get('last_result') == 'success':
                    completed_cases += 1
                elif case_data.get('last_result') == 'failure':
                    failed_cases += 1
        
        progress_percentage = (completed_cases / total_cases * 100) if total_cases > 0 else 0
        
        return {
            'total_cases': total_cases,
            'completed_cases': completed_cases,
            'failed_cases': failed_cases,
            'progress_percentage': progress_percentage
        }


# Global instance
_instance = None 