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
            # Handle empty config data by providing defaults
            if not config_data:
                config_data = {'protocol_type': 'unknown'}
            
            # Ensure protocol_type is always present
            if 'protocol_type' not in config_data:
                config_data['protocol_type'] = 'unknown'
            
            # Validate configuration (will now always pass basic validation)
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
    
    # Generator Configuration Management
    def get_generator_config(self, generator_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get generator configuration
        
        Args:
            generator_id: Optional generator ID to get specific config
            
        Returns:
            Dict: Generator configuration
        """
        try:
            if generator_id:
                if generator_id not in self.generator_configs:
                    raise Exception(f"Generator config {generator_id} not found")
                return self.generator_configs[generator_id]
            
            # Return default generator config if no ID specified
            return {
                'type': 'radamsa',
                'mutation_rate': 0.1,
                'seed_corpus': [],
                'max_mutations': 1000,
                'timeout_seconds': 1.0,
                'min_length': 1,
                'max_length': 1024,
                'preserve_structure': False,
                'generators': [
                    {
                        'name': 'radamsa',
                        'description': 'Grammar-based fuzzer',
                        'parameters': {
                            'mutation_rate': 0.1,
                            'seed_corpus': []
                        }
                    },
                    {
                        'name': 'random',
                        'description': 'Random data generator',
                        'parameters': {
                            'min_length': 1,
                            'max_length': 1024
                        }
                    },
                    {
                        'name': 'bit_flip',
                        'description': 'Bit-flipping mutator',
                        'parameters': {
                            'flip_probability': 0.01
                        }
                    }
                ]
            }
            
        except Exception as e:
            logger.error(f"Error getting generator config: {str(e)}")
            raise
    
    def save_generator_config(self, config_data: Dict[str, Any]) -> str:
        """
        Save generator configuration
        
        Args:
            config_data: Generator configuration data
            
        Returns:
            str: Configuration ID
        """
        try:
            # Generate config ID
            config_id = str(uuid.uuid4())
            
            # Save config
            config_entry = {
                'id': config_id,
                'type': config_data.get('type', 'radamsa'),
                'mutation_rate': config_data.get('mutation_rate', 0.1),
                'seed_corpus': config_data.get('seed_corpus', []),
                'max_mutations': config_data.get('max_mutations', 1000),
                'timeout_seconds': config_data.get('timeout_seconds', 1.0),
                'min_length': config_data.get('min_length', 1),
                'max_length': config_data.get('max_length', 1024),
                'preserve_structure': config_data.get('preserve_structure', False),
                'created_at': datetime.now().isoformat()
            }
            
            self.generator_configs[config_id] = config_entry
            
            logger.info(f"Generator config {config_id} saved successfully")
            return config_id
            
        except Exception as e:
            logger.error(f"Error saving generator config: {str(e)}")
            raise
    
    # Protocol Frame Management
    def build_protocol_frame(self, frame_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build protocol frame from configuration
        
        Args:
            frame_config: Frame configuration
            
        Returns:
            Dict: Built protocol frame
        """
        try:
            protocol_type = frame_config.get('protocol_type', 'can')
            frame_data = frame_config.get('frame_data', {})
            
            # Build frame based on protocol type
            if protocol_type == 'can':
                frame = self._build_can_frame(frame_data)
            elif protocol_type == 'uart':
                frame = self._build_uart_frame(frame_data)
            elif protocol_type == 'spi':
                frame = self._build_spi_frame(frame_data)
            elif protocol_type == 'ethernet':
                frame = self._build_ethernet_frame(frame_data)
            elif protocol_type == 'doip':
                frame = self._build_doip_frame(frame_data)
            else:
                raise ValueError(f"Unsupported protocol type: {protocol_type}")
            
            return {
                'status': 'success',
                'protocol_type': protocol_type,
                'frame': frame,
                'frame_size': len(frame.get('data', [])),
                'checksum': self._calculate_checksum(frame.get('data', []))
            }
            
        except Exception as e:
            logger.error(f"Error building protocol frame: {str(e)}")
            raise
    
    def validate_protocol_frame(self, frame_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate protocol frame structure
        
        Args:
            frame_data: Frame data to validate
            
        Returns:
            Dict: Validation result
        """
        try:
            protocol_type = frame_data.get('protocol_type', 'can')
            frame = frame_data.get('frame', {})
            
            validation_result = {
                'valid': False,
                'errors': [],
                'warnings': [],
                'frame_info': {}
            }
            
            # Validate based on protocol type
            if protocol_type == 'can':
                validation_result = self._validate_can_frame(frame)
            elif protocol_type == 'uart':
                validation_result = self._validate_uart_frame(frame)
            elif protocol_type == 'spi':
                validation_result = self._validate_spi_frame(frame)
            elif protocol_type == 'ethernet':
                validation_result = self._validate_ethernet_frame(frame)
            elif protocol_type == 'doip':
                validation_result = self._validate_doip_frame(frame)
            else:
                validation_result['errors'].append(f"Unsupported protocol type: {protocol_type}")
            
            validation_result['valid'] = len(validation_result['errors']) == 0
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Error validating protocol frame: {str(e)}")
            raise
    
    def get_protocol_frame_templates(self, protocol_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get available protocol frame templates
        
        Args:
            protocol_type: Optional protocol type to filter templates
            
        Returns:
            List[Dict]: List of frame templates
        """
        try:
            templates = [
                {
                    'id': 'can_diagnostic',
                    'name': 'CAN Diagnostic Frame',
                    'protocol_type': 'can',
                    'description': 'Standard CAN diagnostic frame template',
                    'template': {
                        'id': 0x7DF,
                        'extended': False,
                        'data': [0x02, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
                    }
                },
                {
                    'id': 'can_extended',
                    'name': 'CAN Extended Frame',
                    'protocol_type': 'can',
                    'description': 'Extended CAN frame template',
                    'template': {
                        'id': 0x18DAF110,
                        'extended': True,
                        'data': [0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
                    }
                },
                {
                    'id': 'uart_at_command',
                    'name': 'UART AT Command',
                    'protocol_type': 'uart',
                    'description': 'AT command over UART template',
                    'template': {
                        'data': 'AT+CGMI\r\n',
                        'encoding': 'ascii',
                        'terminator': '\r\n'
                    }
                },
                {
                    'id': 'doip_diagnostic',
                    'name': 'DoIP Diagnostic Request',
                    'protocol_type': 'doip',
                    'description': 'DoIP diagnostic message template',
                    'template': {
                        'protocol_version': 0x02,
                        'payload_type': 0x8001,
                        'source_address': 0x0E80,
                        'target_address': 0x1000,
                        'data': [0x22, 0xF1, 0x90]
                    }
                }
            ]
            
            # Filter by protocol type if specified
            if protocol_type:
                templates = [t for t in templates if t['protocol_type'] == protocol_type]
            
            return templates
            
        except Exception as e:
            logger.error(f"Error getting protocol frame templates: {str(e)}")
            raise
    
    # Export/Import Management
    def export_test_data(self, export_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Export test data (groups, cases, results)
        
        Args:
            export_config: Export configuration
            
        Returns:
            Dict: Export result with data
        """
        try:
            export_type = export_config.get('type', 'json')
            include_groups = export_config.get('include_groups', True)
            include_cases = export_config.get('include_cases', True)
            include_results = export_config.get('include_results', False)
            
            export_data = {
                'export_info': {
                    'timestamp': datetime.now().isoformat(),
                    'version': '1.0',
                    'type': export_type
                }
            }
            
            if include_groups:
                export_data['test_groups'] = list(self.test_groups.values())
            
            if include_cases:
                export_data['test_cases'] = list(self.test_cases.values())
            
            if include_results:
                # This would include fuzzing results - for now return empty
                export_data['fuzzing_results'] = []
            
            return {
                'status': 'success',
                'export_data': export_data,
                'export_size': len(json.dumps(export_data)),
                'export_type': export_type
            }
            
        except Exception as e:
            logger.error(f"Error exporting test data: {str(e)}")
            raise
    
    def import_test_data(self, import_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Import test data (groups, cases, results)
        
        Args:
            import_data: Import data
            
        Returns:
            Dict: Import result
        """
        try:
            imported_groups = 0
            imported_cases = 0
            errors = []
            
            # Import test groups
            if 'test_groups' in import_data:
                for group_data in import_data['test_groups']:
                    try:
                        group_id = group_data.get('id', str(uuid.uuid4()))
                        self.test_groups[group_id] = group_data
                        imported_groups += 1
                    except Exception as e:
                        errors.append(f"Error importing group {group_data.get('id', 'unknown')}: {str(e)}")
            
            # Import test cases
            if 'test_cases' in import_data:
                for case_data in import_data['test_cases']:
                    try:
                        case_id = case_data.get('id', str(uuid.uuid4()))
                        self.test_cases[case_id] = case_data
                        imported_cases += 1
                    except Exception as e:
                        errors.append(f"Error importing case {case_data.get('id', 'unknown')}: {str(e)}")
            
            return {
                'status': 'success',
                'imported_groups': imported_groups,
                'imported_cases': imported_cases,
                'errors': errors,
                'total_errors': len(errors)
            }
            
        except Exception as e:
            logger.error(f"Error importing test data: {str(e)}")
            raise
    
    # File Management
    def get_files_tree(self, root_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Get files tree structure for results
        
        Args:
            root_path: Optional root path filter
            
        Returns:
            Dict: Files tree structure
        """
        try:
            import os
            
            # Default results path
            if not root_path:
                root_path = '/tmp/fuzzer_results'
            
            # Create directory if it doesn't exist
            if not os.path.exists(root_path):
                os.makedirs(root_path, exist_ok=True)
            
            def build_tree(path: str) -> Dict[str, Any]:
                """Build file tree recursively"""
                items = []
                
                try:
                    for item in os.listdir(path):
                        item_path = os.path.join(path, item)
                        
                        if os.path.isdir(item_path):
                            items.append({
                                'name': item,
                                'type': 'directory',
                                'path': item_path,
                                'children': build_tree(item_path)
                            })
                        else:
                            stat = os.stat(item_path)
                            items.append({
                                'name': item,
                                'type': 'file',
                                'path': item_path,
                                'size': stat.st_size,
                                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                            })
                except PermissionError:
                    pass
                
                return items
            
            tree = {
                'root': root_path,
                'tree': build_tree(root_path),
                'total_files': self._count_files(root_path),
                'total_size': self._calculate_directory_size(root_path)
            }
            
            return tree
            
        except Exception as e:
            logger.error(f"Error getting files tree: {str(e)}")
            raise
    
    # Results Management
    def export_results(self, export_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Export fuzzing results
        
        Args:
            export_config: Export configuration
            
        Returns:
            Dict: Export result
        """
        try:
            export_format = export_config.get('format', 'json')
            campaign_id = export_config.get('campaign_id')
            include_logs = export_config.get('include_logs', True)
            include_crashes = export_config.get('include_crashes', True)
            
            results_data = {
                'export_info': {
                    'timestamp': datetime.now().isoformat(),
                    'campaign_id': campaign_id,
                    'format': export_format
                },
                'summary': {
                    'total_iterations': 0,
                    'crashes_found': 0,
                    'timeouts': 0,
                    'errors': 0
                }
            }
            
            if include_logs:
                results_data['logs'] = []  # This would include actual log data
            
            if include_crashes:
                results_data['crashes'] = []  # This would include crash data
            
            return {
                'status': 'success',
                'results_data': results_data,
                'export_format': export_format,
                'export_size': len(json.dumps(results_data))
            }
            
        except Exception as e:
            logger.error(f"Error exporting results: {str(e)}")
            raise
    
    # Private helper methods for protocol frame building
    def _build_can_frame(self, frame_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build CAN frame"""
        return {
            'id': frame_data.get('id', 0x7DF),
            'extended': frame_data.get('extended', False),
            'data': frame_data.get('data', [0x02, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        }
    
    def _build_uart_frame(self, frame_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build UART frame"""
        return {
            'data': frame_data.get('data', 'AT+CGMI\r\n'),
            'encoding': frame_data.get('encoding', 'ascii'),
            'terminator': frame_data.get('terminator', '\r\n')
        }
    
    def _build_spi_frame(self, frame_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build SPI frame"""
        return {
            'data': frame_data.get('data', [0x01, 0x02, 0x03, 0x04]),
            'mode': frame_data.get('mode', 0),
            'speed': frame_data.get('speed', 1000000)
        }
    
    def _build_ethernet_frame(self, frame_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build Ethernet frame"""
        return {
            'destination': frame_data.get('destination', 'ff:ff:ff:ff:ff:ff'),
            'source': frame_data.get('source', '00:00:00:00:00:00'),
            'type': frame_data.get('type', 0x0800),
            'data': frame_data.get('data', [])
        }
    
    def _build_doip_frame(self, frame_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build DoIP frame"""
        return {
            'protocol_version': frame_data.get('protocol_version', 0x02),
            'payload_type': frame_data.get('payload_type', 0x8001),
            'source_address': frame_data.get('source_address', 0x0E80),
            'target_address': frame_data.get('target_address', 0x1000),
            'data': frame_data.get('data', [0x22, 0xF1, 0x90])
        }
    
    # Private helper methods for protocol frame validation
    def _validate_can_frame(self, frame: Dict[str, Any]) -> Dict[str, Any]:
        """Validate CAN frame"""
        result = {'valid': True, 'errors': [], 'warnings': [], 'frame_info': {}}
        
        # Validate ID
        can_id = frame.get('id', 0)
        if can_id < 0 or can_id > 0x1FFFFFFF:
            result['errors'].append("CAN ID out of range")
        
        # Validate data length
        data = frame.get('data', [])
        if len(data) > 8:
            result['errors'].append("CAN data length exceeds 8 bytes")
        
        result['frame_info']['id'] = can_id
        result['frame_info']['extended'] = frame.get('extended', False)
        result['frame_info']['data_length'] = len(data)
        
        return result
    
    def _validate_uart_frame(self, frame: Dict[str, Any]) -> Dict[str, Any]:
        """Validate UART frame"""
        result = {'valid': True, 'errors': [], 'warnings': [], 'frame_info': {}}
        
        data = frame.get('data', '')
        if not data:
            result['errors'].append("UART data is empty")
        
        result['frame_info']['data_length'] = len(data)
        result['frame_info']['encoding'] = frame.get('encoding', 'ascii')
        
        return result
    
    def _validate_spi_frame(self, frame: Dict[str, Any]) -> Dict[str, Any]:
        """Validate SPI frame"""
        result = {'valid': True, 'errors': [], 'warnings': [], 'frame_info': {}}
        
        data = frame.get('data', [])
        if not data:
            result['errors'].append("SPI data is empty")
        
        result['frame_info']['data_length'] = len(data)
        result['frame_info']['mode'] = frame.get('mode', 0)
        
        return result
    
    def _validate_ethernet_frame(self, frame: Dict[str, Any]) -> Dict[str, Any]:
        """Validate Ethernet frame"""
        result = {'valid': True, 'errors': [], 'warnings': [], 'frame_info': {}}
        
        # Basic validation
        if 'destination' not in frame:
            result['errors'].append("Missing destination MAC address")
        if 'source' not in frame:
            result['errors'].append("Missing source MAC address")
        
        return result
    
    def _validate_doip_frame(self, frame: Dict[str, Any]) -> Dict[str, Any]:
        """Validate DoIP frame"""
        result = {'valid': True, 'errors': [], 'warnings': [], 'frame_info': {}}
        
        # Validate protocol version
        version = frame.get('protocol_version', 0)
        if version != 0x02:
            result['warnings'].append(f"Non-standard protocol version: {version}")
        
        result['frame_info']['protocol_version'] = version
        result['frame_info']['payload_type'] = frame.get('payload_type', 0)
        
        return result
    
    def _calculate_checksum(self, data: List[int]) -> int:
        """Calculate simple checksum"""
        return sum(data) & 0xFF
    
    def _count_files(self, path: str) -> int:
        """Count files in directory recursively"""
        try:
            import os
            count = 0
            for root, dirs, files in os.walk(path):
                count += len(files)
            return count
        except:
            return 0
    
    def _calculate_directory_size(self, path: str) -> int:
        """Calculate total directory size"""
        try:
            import os
            total_size = 0
            for root, dirs, files in os.walk(path):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        total_size += os.path.getsize(file_path)
                    except:
                        pass
            return total_size
        except:
            return 0
    
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