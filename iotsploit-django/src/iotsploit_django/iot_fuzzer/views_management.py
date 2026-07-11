from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpRequest
import json
import logging

from iotsploit_django.iot_fuzzer.service import (
    IoTFuzzerService,
)
from iotsploit_django.iot_fuzzer.http import method_not_allowed

# Import Django models
from iotsploit_django.adapters.django.iot_fuzzer.models import (
    FuzzingCampaign, TestGroup, TestCase, ProtocolConfiguration, FrameField
)

logger = logging.getLogger(__name__)

# Campaign Control Endpoints

def get_test_groups_list(request: HttpRequest):
    """
    GET /api/iot-fuzzer/management/test-groups/list/
    Return all test groups with metadata
    """
    if request.method != 'GET':
        return method_not_allowed("GET")
    
    try:
        campaign_id = request.GET.get('campaign_id')
        
        test_groups = TestGroup.objects.select_related('campaign').prefetch_related('test_cases')
        
        if campaign_id:
            test_groups = test_groups.filter(campaign_id=campaign_id)
        
        groups_data = []
        for group in test_groups:
            groups_data.append({
                'id': group.id,
                'name': group.name,
                'description': group.description,
                'campaign_id': group.campaign.id if group.campaign else None,
                'campaign_name': group.campaign.name if group.campaign else 'No Campaign',
                'priority': group.priority,
                'enabled': group.enabled,
                'protocol_type': group.protocol_type,
                'total_cases': group.total_cases,
                'completed_cases': group.completed_cases,
                'failed_cases': group.failed_cases,
                'completion_percentage': group.get_completion_percentage(),
                'created_at': group.created_at.isoformat()
            })
        
        return JsonResponse({
            "status": "success",
            "test_groups": groups_data
        })
        
    except Exception as e:
        logger.error(f"Error getting test groups list: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get test groups list: {str(e)}"
        }, status=500)

@csrf_exempt
def create_test_group(request: HttpRequest):
    """
    POST /api/iot-fuzzer/management/test-groups/create/
    Create new test group
    """
    if request.method != 'POST':
        return method_not_allowed("POST")
    
    try:
        data = json.loads(request.body)
        
        # Handle both nested and flat data formats
        if 'group' in data:
            group_data = data.get('group', {})
        else:
            group_data = data
        
        campaign_id = group_data.get('campaign_id')
        if not campaign_id:
            # Create or get default campaign if none provided
            campaign, created = FuzzingCampaign.objects.get_or_create(
                name='Default Campaign',
                defaults={
                    'description': 'Default campaign for test groups',
                    'protocol_type': group_data.get('protocol_type', 'can'),
                    'status': 'idle'
                }
            )
        else:
            try:
                campaign = FuzzingCampaign.objects.get(id=campaign_id)
            except FuzzingCampaign.DoesNotExist:
                return JsonResponse({
                    "status": "error",
                    "message": f"Campaign with ID {campaign_id} not found"
                }, status=404)
            except ValueError:
                return JsonResponse({
                    "status": "error",
                    "message": f"Invalid campaign ID format: {campaign_id}"
                }, status=400)
        
        test_group = TestGroup.objects.create(
            name=group_data.get('name', ''),
            description=group_data.get('description', ''),
            campaign=campaign,
            priority=group_data.get('priority', 'normal'),
            enabled=group_data.get('enabled', True),
            protocol_type=group_data.get('protocol_type', campaign.protocol_type)
        )
        
        return JsonResponse({
            "status": "success",
            "group_id": test_group.id,
            "message": "Test group created successfully"
        })
        
    except FuzzingCampaign.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Campaign not found"
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error creating test group: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to create test group: {str(e)}"
        }, status=500)

@csrf_exempt
def update_test_group(request: HttpRequest, group_id):
    """
    PUT /api/iot-fuzzer/management/test-groups/update/<id>/
    Update test group properties
    """
    if request.method != 'PUT':
        return method_not_allowed("PUT")
    
    try:
        data = json.loads(request.body)
        group_data = data.get('group', {})
        
        test_group = TestGroup.objects.get(id=group_id)
        
        # Update fields
        if 'name' in group_data:
            test_group.name = group_data['name']
        if 'description' in group_data:
            test_group.description = group_data['description']
        if 'priority' in group_data:
            test_group.priority = group_data['priority']
        if 'enabled' in group_data:
            test_group.enabled = group_data['enabled']
        
        test_group.save()
        
        return JsonResponse({
            "status": "success",
            "message": "Test group updated successfully"
        })
        
    except TestGroup.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Test group not found"
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error updating test group: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to update test group: {str(e)}"
        }, status=500)

@csrf_exempt
def delete_test_group(request: HttpRequest, group_id):
    """
    DELETE /api/iot-fuzzer/management/test-groups/delete/<id>/
    Delete test group and associated test cases
    """
    if request.method != 'DELETE':
        return method_not_allowed("DELETE")
    
    try:
        test_group = TestGroup.objects.get(id=group_id)
        test_group.delete()
        
        return JsonResponse({
            "status": "success",
            "message": "Test group deleted successfully"
        })
        
    except TestGroup.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Test group not found"
        }, status=404)
    except Exception as e:
        logger.error(f"Error deleting test group: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to delete test group: {str(e)}"
        }, status=500)

def get_test_cases_list(request: HttpRequest):
    """
    GET /api/iot-fuzzer/management/test-cases/list/
    Return test cases with group assignment
    """
    if request.method != 'GET':
        return method_not_allowed("GET")
    
    try:
        group_id = request.GET.get('group_id')
        campaign_id = request.GET.get('campaign_id')
        
        test_cases = TestCase.objects.select_related('group', 'group__campaign', 'protocol_config').prefetch_related('frame_fields', 'fuzzing_rules')
        
        if group_id:
            test_cases = test_cases.filter(group_id=group_id)
        elif campaign_id:
            test_cases = test_cases.filter(group__campaign_id=campaign_id)
        
        cases_data = []
        for case in test_cases:
            # Build protocol frame from frame fields for backward compatibility
            protocol_frame = {}
            for field in case.frame_fields.order_by('field_order'):
                protocol_frame[field.field_id] = field.value
            
            # Get fuzzing rules summary
            fuzzing_targets = case.get_fuzzing_targets()
            
            cases_data.append({
                'id': case.id,
                'name': case.name,
                'description': case.description,
                'group_id': case.group.id if case.group else None,
                'group_name': case.group.name if case.group else 'No Group',
                'campaign_id': case.group.campaign.id if case.group and case.group.campaign else None,
                'campaign_name': case.group.campaign.name if case.group and case.group.campaign else 'No Campaign',
                'priority': case.priority,
                'enabled': case.enabled,
                'protocol_frame': protocol_frame,  # Reconstructed from frame fields
                'frame_name': case.frame_name,
                'frame_description': case.frame_description,
                'protocol_type': case.protocol_config.protocol_type if case.protocol_config else 'unknown',
                'protocol_settings': case.protocol_config.settings if case.protocol_config else {},
                'fuzzing_targets': fuzzing_targets,
                'expected_response': case.expected_response,
                'timeout_seconds': case.timeout_seconds,
                'timeout': int(case.timeout_seconds * 1000),  # Convert to milliseconds for Flutter
                'iterations': case.iterations,  # Now an actual field in the model
                'execution_count': case.execution_count,
                'last_executed': case.last_executed.isoformat() if case.last_executed else None,
                'last_result': case.last_result,
                'created_at': case.created_at.isoformat()
            })
        
        return JsonResponse({
            "status": "success",
            "test_cases": cases_data
        })
        
    except Exception as e:
        logger.error(f"Error getting test cases list: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get test cases list: {str(e)}"
        }, status=500)

@csrf_exempt
def create_test_case(request: HttpRequest):
    """
    POST /api/iot-fuzzer/management/test-cases/create/
    Create new test case
    """
    if request.method != 'POST':
        return method_not_allowed("POST")
    
    try:
        data = json.loads(request.body)
        # Support both nested (case: {}) and flat data formats
        case_data = data.get('case', data)

        print(f"test_case_data: {case_data}")
        
        group_id = case_data.get('group_id')
        if not group_id:
            return JsonResponse({
                "status": "error",
                "message": "Group ID is required"
            }, status=400)
        
        # Handle both string and integer group IDs
        try:
            # Try to find by integer ID first
            if isinstance(group_id, str) and group_id.isdigit():
                group = TestGroup.objects.get(id=int(group_id))
            elif isinstance(group_id, int):
                group = TestGroup.objects.get(id=group_id)
            else:
                # If it's a string ID like 'offline-group-1', create a default group first
                if group_id.startswith('offline-'):
                    # Create or get default campaign if none exists
                    campaign, created = FuzzingCampaign.objects.get_or_create(
                        name='Default Campaign',
                        defaults={
                            'description': 'Default campaign for test cases',
                            'protocol_type': 'can',
                            'status': 'idle'
                        }
                    )
                    
                    # Create the group if it doesn't exist
                    group, created = TestGroup.objects.get_or_create(
                        name=case_data.get('name', 'Default Group'),
                        campaign=campaign,
                        defaults={
                            'description': 'Default test group',
                            'protocol_type': 'can',
                            'priority': 'normal',
                            'enabled': True
                        }
                    )
                else:
                    return JsonResponse({
                        "status": "error",
                        "message": f"Invalid group ID format: {group_id}"
                    }, status=400)
        except (TestGroup.DoesNotExist, ValueError):
            return JsonResponse({
                "status": "error",
                "message": f"Test group with ID {group_id} not found"
            }, status=404)
        
        # Convert timeout from milliseconds to seconds if needed
        timeout_value = case_data.get('timeout', case_data.get('timeout_seconds', 1.0))
        if timeout_value > 100:  # Assume it's in milliseconds if > 100
            timeout_value = timeout_value / 1000.0
        
        # Get or create a default protocol configuration
        protocol_type = (case_data.get('protocol_type') or group.protocol_type or '').lower()
        default_settings = {'default': True}
        if protocol_type == 'can':
            # Use bitrate and device_path for CAN
            default_settings.update({'bitrate': 500000, 'device_path': 'can0'})
        elif protocol_type == 'uart':
            default_settings.update({'baud_rate': 115200, 'port': '/dev/ttyUSB0', 'timeout': 1000})

        protocol_config, created = ProtocolConfiguration.objects.get_or_create(
            protocol_type=protocol_type,
            defaults={'settings': default_settings}
        )
        
        test_case = TestCase.objects.create(
            name=case_data.get('name', ''),
            description=case_data.get('description', ''),
            group=group,
            protocol_config=protocol_config,
            frame_name=case_data.get('frame_name', 'Protocol Frame'),
            frame_description=case_data.get('frame_description', ''),
            priority=case_data.get('priority', 'normal'),
            enabled=case_data.get('enabled', True),
            expected_response=case_data.get('expected_response'),
            timeout_seconds=timeout_value,
            iterations=case_data.get('iterations', 100)
        )
        
        # Create frame fields from protocol_frame data (for backward compatibility)
        protocol_frame = case_data.get('protocol_frame', {})
        if protocol_frame:
            field_order = 1
            for field_id, value in protocol_frame.items():
                FrameField.objects.create(
                    test_case=test_case,
                    field_name=field_id.replace('_', ' ').title(),
                    field_id=field_id,
                    field_type='hex' if isinstance(value, str) and value.startswith('0x') else 'dec',
                    value=str(value),
                    field_order=field_order,
                    is_required=(field_id in ['service_id', 'sid', 'id'])
                )
                field_order += 1
        
        # Update group statistics
        group.update_statistics()
        
        return JsonResponse({
            "status": "success",
            "case_id": test_case.id,
            "message": "Test case created successfully"
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error creating test case: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to create test case: {str(e)}"
        }, status=500)

@csrf_exempt
def update_test_case(request: HttpRequest, case_id):
    """
    PUT /api/iot-fuzzer/management/test-cases/update/<id>/
    Update test case properties
    """
    if request.method != 'PUT':
        return method_not_allowed("PUT")
    
    try:
        data = json.loads(request.body)
        case_data = data.get('case', {})

        print(f"update test_case_data: {case_data}")
        
        test_case = TestCase.objects.get(id=case_id)
        
        # Update fields
        if 'name' in case_data:
            test_case.name = case_data['name']
        if 'description' in case_data:
            test_case.description = case_data['description']
        if 'frame_name' in case_data:
            test_case.frame_name = case_data['frame_name']
        if 'frame_description' in case_data:
            test_case.frame_description = case_data['frame_description']
        if 'priority' in case_data:
            test_case.priority = case_data['priority']
        if 'enabled' in case_data:
            test_case.enabled = case_data['enabled']
        if 'expected_response' in case_data:
            test_case.expected_response = case_data['expected_response']
        if 'timeout_seconds' in case_data:
            test_case.timeout_seconds = case_data['timeout_seconds']
        if 'iterations' in case_data:
            test_case.iterations = case_data['iterations']
        
        # Handle protocol_type updates
        if 'protocol_type' in case_data:
            protocol_type = case_data['protocol_type']
            # Find or create ProtocolConfiguration for this protocol type
            protocol_config, created = ProtocolConfiguration.objects.get_or_create(
                protocol_type=protocol_type,
                defaults={'settings': {}}
            )
            test_case.protocol_config = protocol_config
        
        # Handle protocol_frame updates by updating frame fields
        if 'protocol_frame' in case_data:
            protocol_frame = case_data['protocol_frame']
            
            # Update existing frame fields or create new ones
            existing_fields = {f.field_id: f for f in test_case.frame_fields.all()}
            
            field_order = 1
            for field_id, value in protocol_frame.items():
                if field_id in existing_fields:
                    # Update existing field
                    field = existing_fields[field_id]
                    field.value = str(value)
                    field.save()
                else:
                    # Create new field
                    FrameField.objects.create(
                        test_case=test_case,
                        field_name=field_id.replace('_', ' ').title(),
                        field_id=field_id,
                        field_type='hex' if isinstance(value, str) and value.startswith('0x') else 'dec',
                        value=str(value),
                        field_order=field_order,
                        is_required=(field_id in ['service_id', 'sid', 'id'])
                    )
                field_order += 1
        
        test_case.save()
        
        return JsonResponse({
            "status": "success",
            "message": "Test case updated successfully"
        })
        
    except TestCase.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Test case not found"
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error updating test case: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to update test case: {str(e)}"
        }, status=500)

@csrf_exempt
def delete_test_case(request: HttpRequest, case_id):
    """
    DELETE /api/iot-fuzzer/management/test-cases/delete/<id>/
    Delete test case
    """
    if request.method != 'DELETE':
        return method_not_allowed("DELETE")
    
    try:
        test_case = TestCase.objects.get(id=case_id)
        group = test_case.group
        test_case.delete()
        
        # Update group statistics
        group.update_statistics()
        
        return JsonResponse({
            "status": "success",
            "message": "Test case deleted successfully"
        })
        
    except TestCase.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Test case not found"
        }, status=404)
    except Exception as e:
        logger.error(f"Error deleting test case: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to delete test case: {str(e)}"
        }, status=500)

@csrf_exempt
def move_test_case(request: HttpRequest):
    """
    POST /api/iot-fuzzer/management/test-cases/move/
    Move test case between groups
    """
    if request.method != 'POST':
        return method_not_allowed("POST")
    
    try:
        data = json.loads(request.body)
        # Support both case_id and test_case_id field names
        case_id = data.get('case_id') or data.get('test_case_id')
        target_group_id = data.get('target_group_id')
        
        if not case_id:
            return JsonResponse({
                "status": "error",
                "message": "Test case ID is required"
            }, status=400)
        
        if not target_group_id:
            return JsonResponse({
                "status": "error",
                "message": "Target group ID is required"
            }, status=400)
        
        try:
            test_case = TestCase.objects.get(id=case_id)
        except TestCase.DoesNotExist:
            return JsonResponse({
                "status": "error",
                "message": "Test case not found"
            }, status=404)
        
        try:
            # Handle both string and integer group IDs
            if isinstance(target_group_id, str) and target_group_id.isdigit():
                new_group = TestGroup.objects.get(id=int(target_group_id))
            elif isinstance(target_group_id, int):
                new_group = TestGroup.objects.get(id=target_group_id)
            else:
                return JsonResponse({
                    "status": "error",
                    "message": f"Invalid target group ID format: {target_group_id}"
                }, status=400)
        except TestGroup.DoesNotExist:
            return JsonResponse({
                "status": "error",
                "message": "Target group not found"
            }, status=404)
        
        old_group = test_case.group
        
        # Validate group compatibility
        if old_group.campaign != new_group.campaign:
            return JsonResponse({
                "status": "error",
                "message": "Cannot move test case to different campaign"
            }, status=400)
        
        test_case.group = new_group
        test_case.save()
        
        # Update statistics for both groups
        old_group.update_statistics()
        new_group.update_statistics()
        
        return JsonResponse({
            "status": "success",
            "message": "Test case moved successfully"
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error moving test case: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to move test case: {str(e)}"
        }, status=500)

@csrf_exempt
def build_protocol_frame(request: HttpRequest):
    """
    POST /api/iot-fuzzer/management/protocol-frames/build/
    Build protocol frame from field specifications
    """
    if request.method != 'POST':
        return method_not_allowed("POST")
    
    try:
        data = json.loads(request.body)
        frame_spec = data.get('frame_spec', {})
        
        fuzzer_service = IoTFuzzerService.get_instance()
        frame_data = fuzzer_service.build_protocol_frame(frame_spec)
        
        return JsonResponse({
            "status": "success",
            "frame_data": frame_data
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error building protocol frame: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to build protocol frame: {str(e)}"
        }, status=500)

@csrf_exempt
def validate_protocol_frame(request: HttpRequest):
    """
    POST /api/iot-fuzzer/management/protocol-frames/validate/
    Validate protocol frame structure
    """
    if request.method != 'POST':
        return method_not_allowed("POST")
    
    try:
        data = json.loads(request.body)
        frame_data = data.get('frame_data', {})
        
        fuzzer_service = IoTFuzzerService.get_instance()
        validation_result = fuzzer_service.validate_protocol_frame(frame_data)
        
        return JsonResponse({
            "status": "success",
            "validation_result": validation_result
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error validating protocol frame: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to validate protocol frame: {str(e)}"
        }, status=500)

def get_protocol_frame_templates(request: HttpRequest):
    """
    GET /api/iot-fuzzer/management/protocol-frames/templates/
    Return protocol frame templates
    """
    if request.method != 'GET':
        return method_not_allowed("GET")
    
    try:
        protocol_type = request.GET.get('protocol_type')
        
        fuzzer_service = IoTFuzzerService.get_instance()
        templates = fuzzer_service.get_protocol_frame_templates(protocol_type)
        
        return JsonResponse({
            "status": "success",
            "templates": templates
        })
        
    except Exception as e:
        logger.error(f"Error getting protocol frame templates: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get protocol frame templates: {str(e)}"
        }, status=500)

@csrf_exempt
def export_test_data(request: HttpRequest):
    """
    POST /api/iot-fuzzer/management/export/
    Export test groups and cases
    """
    if request.method != 'POST':
        return method_not_allowed("POST")
    
    try:
        data = json.loads(request.body)
        export_config = data.get('export_config', {})
        
        fuzzer_service = IoTFuzzerService.get_instance()
        export_result = fuzzer_service.export_test_data(export_config)
        
        return JsonResponse({
            "status": "success",
            "export_result": export_result
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error exporting test data: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to export test data: {str(e)}"
        }, status=500)

@csrf_exempt
def import_test_data(request: HttpRequest):
    """
    POST /api/iot-fuzzer/management/import/
    Import test groups and cases
    """
    if request.method != 'POST':
        return method_not_allowed("POST")
    
    try:
        data = json.loads(request.body)
        import_data = data.get('import_data', {})
        
        fuzzer_service = IoTFuzzerService.get_instance()
        import_result = fuzzer_service.import_test_data(import_data)
        
        return JsonResponse({
            "status": "success",
            "import_result": import_result
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error importing test data: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to import test data: {str(e)}"
        }, status=500)

