# IoT Protocol Fuzzer Django Integration TODO List

## 🎯 Project Overview
Integration of IoT Protocol Fuzzer backend with Django to support the Flutter UI with comprehensive API endpoints, real-time communication, and fuzzing campaign management.

**ARCHITECTURE PRINCIPLE**: Zero cross-dependency - Only Django app (`iotsploit`) depends on `iot_protocol_fuzzer`. The fuzzer remains completely independent.

## 📊 Project Analysis Summary

### IoT Protocol Fuzzer Core Components (INDEPENDENT - NO MODIFICATIONS)
- **Orchestrator**: Main fuzzing campaign coordinator (`iot_protocol_fuzzer/core/orchestrator.py`)
- **Generators**: Data mutation engines (Radamsa-based) (`iot_protocol_fuzzer/generators/`)
- **Harnesses**: Protocol-specific execution handlers (`iot_protocol_fuzzer/harnesses/`)
- **Interfaces**: Hardware interface layer (`iot_protocol_fuzzer/interfaces/`)
- **Monitor**: Real-time statistics and crash detection (`iot_protocol_fuzzer/monitoring/`)
- **TestLogger**: Results logging and artifact storage (`iot_protocol_fuzzer/analysis/`)

### Django Integration Layer (ADAPTER PATTERN)
- **Adapter Classes**: Bridge between Django and IoT fuzzer components
- **Service Layer**: Django-specific business logic and orchestration
- **Event Handlers**: Convert fuzzer events to Django/WebSocket events
- **Configuration Mappers**: Transform Django configs to fuzzer configs

### Flutter UI Requirements (4 main pages)
- **Testing Page**: Real-time test execution and monitoring with three-panel layout
- **Configuration Page**: Protocol and fuzzing engine configuration with templates
- **Management Page**: Test case/group management with protocol frame builder
- **Results Page**: Results analysis, file navigation, and live logging

---

## ✅ Phase 1: Backend Architecture Setup

### 1.1 Django Project Structure Setup
- [ ] **Create IoT Fuzzer view handler file**
  - [ ] Create `sat_toolkit/view_handlers/iot_fuzzer_views.py`
  - [ ] Follow existing project pattern with proper imports
  - [ ] Add Django decorators and error handling
  - [ ] Include proper logging configuration

- [ ] **Update main URL configuration**
  - [ ] Add imports to `sat_toolkit/urls.py`
  - [ ] Import IoT fuzzer view functions
  - [ ] Follow existing naming conventions
  - [ ] Add URL patterns to existing `urlpatterns` list

- [ ] **Create service layer structure (Django-only)**
  - [ ] Create `sat_toolkit/tools/iot_fuzzer_manager.py` (Django service layer)
  - [ ] Create `sat_toolkit/tools/iot_fuzzer_service.py` (Business logic layer)
  - [ ] Create `sat_toolkit/tools/iot_protocol_adapter.py` (Adapter for fuzzer components)
  - [ ] Create `sat_toolkit/tools/iot_fuzzer_bridge.py` (Event bridge layer)

### 1.2 IoT Protocol Fuzzer Integration Layer (ADAPTER PATTERN)
- [ ] **Create adapter classes (Django-side only)**
  - [ ] `IoTFuzzerOrchestratorAdapter` - wraps `iot_protocol_fuzzer.core.orchestrator`
  - [ ] `IoTFuzzerMonitorAdapter` - wraps `iot_protocol_fuzzer.monitoring.monitor`
  - [ ] `IoTFuzzerLoggerAdapter` - wraps `iot_protocol_fuzzer.analysis.logger`
  - [ ] `IoTFuzzerGeneratorAdapter` - wraps `iot_protocol_fuzzer.generators`

- [ ] **Create protocol interface adapters (Django-side only)**
  - [ ] `CANInterfaceAdapter` - adapts CAN protocol interface
  - [ ] `UARTInterfaceAdapter` - adapts UART protocol interface
  - [ ] `SPIInterfaceAdapter` - adapts SPI protocol interface
  - [ ] `EthernetInterfaceAdapter` - adapts Ethernet protocol interface
  - [ ] `DoIPInterfaceAdapter` - adapts DoIP protocol interface

- [ ] **Create event bridge system (Django-side only)**
  - [ ] `FuzzerEventHandler` - converts fuzzer events to Django events
  - [ ] `CampaignStatusBridge` - bridges status updates to WebSocket
  - [ ] `ResultEventBridge` - bridges test results to Django models
  - [ ] `LogEventBridge` - bridges fuzzer logs to Django logging

- [ ] **Add dependency management (Django-side only)**
  - [ ] Check and install required packages (`python-can`, `pyserial`, `spidev`)
  - [ ] Add radamsa binary detection and configuration
  - [ ] Handle missing dependencies gracefully with fallbacks
  - [ ] Add system requirements validation with detailed error reporting
  - [ ] Create dependency checker service

### 1.3 WebSocket and Real-time Support (Django-only)
- [ ] **Configure Django Channels**
  - [ ] Add `channels` to requirements if not present
  - [ ] Update `sat_django_entry/settings.py` with Channels configuration
  - [ ] Create `sat_toolkit/consumers/iot_fuzzer_consumer.py`
  - [ ] Add WebSocket routing to existing routing configuration

- [ ] **Create background task support (Django-only)**
  - [ ] Verify Celery configuration exists
  - [ ] Create `sat_toolkit/tasks/iot_fuzzer_tasks.py`
  - [ ] Add fuzzing campaign background tasks
  - [ ] Implement task status monitoring
  - [ ] Add task result handling and cleanup

---

## ✅ Phase 2: Data Models & Database (Django-only)

### 2.1 Core Database Models (Pure Django - No fuzzer dependencies)
- [ ] **Create IoT Fuzzer models file**
  - [ ] Create `sat_toolkit/models/IoTFuzzer_Model.py`
  - [ ] Follow existing model patterns in the project
  - [ ] Add proper relationships and constraints
  - [ ] Include JSON field support for complex configurations
  - [ ] NO direct imports from iot_protocol_fuzzer

- [ ] **FuzzingCampaign Model** (Pure Django)
  ```python
  class FuzzingCampaign(models.Model):
      # Campaign identification
      name = models.CharField(max_length=255)
      description = models.TextField(blank=True)
      created_at = models.DateTimeField(auto_now_add=True)
      updated_at = models.DateTimeField(auto_now=True)
      
      # Campaign configuration (JSON - no fuzzer coupling)
      protocol_type = models.CharField(max_length=50)
      protocol_config = models.JSONField()
      generator_config = models.JSONField()
      monitoring_config = models.JSONField()
      
      # Campaign state (Django-managed)
      status = models.CharField(max_length=20, default='idle')
      iterations_total = models.IntegerField(default=0)
      iterations_completed = models.IntegerField(default=0)
      
      # Results summary (Django-calculated)
      crashes_found = models.IntegerField(default=0)
      timeouts_occurred = models.IntegerField(default=0)
      errors_encountered = models.IntegerField(default=0)
      
      # Timing information (Django-managed)
      started_at = models.DateTimeField(null=True, blank=True)
      completed_at = models.DateTimeField(null=True, blank=True)
      duration_seconds = models.IntegerField(default=0)
      
      # Adapter instance tracking (Django-internal)
      fuzzer_instance_id = models.CharField(max_length=100, blank=True)
  ```

- [ ] **TestGroup Model** (Pure Django)
  ```python
  class TestGroup(models.Model):
      name = models.CharField(max_length=255)
      description = models.TextField(blank=True)
      campaign = models.ForeignKey(FuzzingCampaign, on_delete=models.CASCADE)
      priority = models.CharField(max_length=20, default='normal')
      enabled = models.BooleanField(default=True)
      created_at = models.DateTimeField(auto_now_add=True)
      
      # Group properties (Django-managed)
      protocol_type = models.CharField(max_length=50)
      mutation_strategy = models.CharField(max_length=50)
      
      # Statistics (Django-calculated)
      total_cases = models.IntegerField(default=0)
      completed_cases = models.IntegerField(default=0)
      failed_cases = models.IntegerField(default=0)
  ```

- [ ] **TestCase Model** (Pure Django)
  ```python
  class TestCase(models.Model):
      name = models.CharField(max_length=255)
      description = models.TextField(blank=True)
      group = models.ForeignKey(TestGroup, on_delete=models.CASCADE)
      
      # Test case configuration (JSON format - no fuzzer coupling)
      protocol_frame = models.JSONField()
      expected_response = models.JSONField(null=True, blank=True)
      timeout_seconds = models.FloatField(default=1.0)
      
      # Test case properties (Django-managed)
      priority = models.CharField(max_length=20, default='normal')
      enabled = models.BooleanField(default=True)
      
      # Execution tracking (Django-managed)
      execution_count = models.IntegerField(default=0)
      last_executed = models.DateTimeField(null=True, blank=True)
      last_result = models.CharField(max_length=20, null=True, blank=True)
  ```

- [ ] **FuzzingResult Model** (Pure Django)
  ```python
  class FuzzingResult(models.Model):
      campaign = models.ForeignKey(FuzzingCampaign, on_delete=models.CASCADE)
      test_case = models.ForeignKey(TestCase, on_delete=models.CASCADE, null=True, blank=True)
      
      # Execution details (Django-captured)
      iteration_number = models.IntegerField()
      executed_at = models.DateTimeField(auto_now_add=True)
      
      # Test payload (from fuzzer via adapter)
      payload_hex = models.TextField()
      payload_size = models.IntegerField()
      
      # Result details (from fuzzer via adapter)
      status = models.CharField(max_length=20)  # success, crash, timeout, error
      response_hex = models.TextField(blank=True)
      response_time_ms = models.FloatField(null=True, blank=True)
      
      # Crash information (from fuzzer via adapter)
      crashed = models.BooleanField(default=False)
      crash_info = models.TextField(blank=True)
      
      # Artifact storage (Django-managed)
      artifact_path = models.CharField(max_length=500, blank=True)
  ```

### 2.2 Configuration and Template Models (Pure Django)
- [ ] **ConfigTemplate Model** (Pure Django)
  ```python
  class ConfigTemplate(models.Model):
      name = models.CharField(max_length=255)
      description = models.TextField(blank=True)
      category = models.CharField(max_length=50)  # automotive, iot, industrial
      
      # Template configuration (JSON format - adapter will convert)
      protocol_config = models.JSONField()
      generator_config = models.JSONField()
      monitoring_config = models.JSONField()
      
      # Template metadata (Django-managed)
      created_at = models.DateTimeField(auto_now_add=True)
      is_default = models.BooleanField(default=False)
      usage_count = models.IntegerField(default=0)
  ```

- [ ] **LiveLog Model** (Pure Django)
  ```python
  class LiveLog(models.Model):
      campaign = models.ForeignKey(FuzzingCampaign, on_delete=models.CASCADE)
      
      # Log entry details (Django-managed)
      timestamp = models.DateTimeField(auto_now_add=True)
      log_level = models.CharField(max_length=20)  # debug, info, warning, error
      message = models.TextField()
      
      # Log categorization (Django-assigned)
      category = models.CharField(max_length=50)  # fuzzer, protocol, system
      source = models.CharField(max_length=100)
      
      # Additional data (from fuzzer via adapter)
      extra_data = models.JSONField(null=True, blank=True)
  ```

### 2.3 Database Setup (Django-only)
- [ ] **Update models __init__.py**
  - [ ] Add import to `sat_toolkit/models/__init__.py`
  - [ ] Follow existing model registration pattern
  - [ ] Ensure proper model discovery

- [ ] **Create and run migrations**
  - [ ] Generate migration: `python manage.py makemigrations sat_toolkit`
  - [ ] Review migration file for correctness
  - [ ] Apply migration: `python manage.py migrate`
  - [ ] Test model creation and relationships

- [ ] **Add model admin interfaces**
  - [ ] Update `sat_toolkit/admin.py` with new models
  - [ ] Add custom admin configurations for better usability
  - [ ] Test admin interface access

---

## ✅ Phase 3: API Endpoints Implementation (Django-only)

### 3.1 Testing Page Endpoints (Pure Django with Adapter Usage)
- [ ] **Campaign Control Endpoints**
  - [ ] `POST /api/iot-fuzzer/testing/campaign/start/`
    - [ ] Validate campaign configuration (Django validation)
    - [ ] Use adapter to initialize IoT Protocol Fuzzer components
    - [ ] Start background fuzzing task (Django Celery)
    - [ ] Return campaign ID and status (Django response)
  
  - [ ] `POST /api/iot-fuzzer/testing/campaign/stop/`
    - [ ] Stop running fuzzing campaign via adapter
    - [ ] Cleanup resources and connections via adapter
    - [ ] Update campaign status in Django database
    - [ ] Return final statistics (Django-calculated)
  
  - [ ] `POST /api/iot-fuzzer/testing/campaign/pause/`
    - [ ] Pause current fuzzing campaign via adapter
    - [ ] Preserve campaign state in Django database
    - [ ] Return pause confirmation (Django response)
  
  - [ ] `POST /api/iot-fuzzer/testing/campaign/reset/`
    - [ ] Reset campaign counters and state (Django models)
    - [ ] Clear previous results if requested (Django database)
    - [ ] Reset adapter state
    - [ ] Return reset confirmation (Django response)

- [ ] **Status and Statistics Endpoints**
  - [ ] `GET /api/iot-fuzzer/testing/campaign/status/`
    - [ ] Return current campaign status (Django model + adapter status)
    - [ ] Include progress information (Django-calculated)
    - [ ] Return real-time statistics (adapter-sourced, Django-formatted)
  
  - [ ] `GET /api/iot-fuzzer/testing/statistics/`
    - [ ] Return detailed campaign statistics (Django-aggregated)
    - [ ] Include performance metrics (adapter-sourced)
    - [ ] Return crash and anomaly data (Django models)
  
  - [ ] `GET /api/iot-fuzzer/testing/test-groups/`
    - [ ] Return test groups with progress (Django models)
    - [ ] Include test cases and status (Django relationships)
    - [ ] Return execution statistics (Django-calculated)

- [ ] **WebSocket for Real-time Updates (Django Channels)**
  - [ ] Create `IoTFuzzerTestingConsumer` WebSocket consumer (Django-only)
  - [ ] Implement connection handling and authentication (Django)
  - [ ] Add real-time campaign status updates (adapter events → WebSocket)
  - [ ] Broadcast test execution progress (adapter events → WebSocket)
  - [ ] Send crash alerts and anomaly notifications (adapter events → WebSocket)

### 3.2 Configuration Page Endpoints (Django with Adapter Configuration)
- [ ] **Protocol Configuration Endpoints**
  - [ ] `GET /api/iot-fuzzer/configuration/protocols/types/`
    - [ ] Return available protocol types via adapter discovery
    - [ ] Include protocol-specific parameters (adapter-provided, Django-formatted)
    - [ ] Return supported features for each protocol (adapter capabilities)
  
  - [ ] `GET /api/iot-fuzzer/configuration/protocols/config/`
    - [ ] Return current protocol configuration (Django model)
    - [ ] Include device paths and connection parameters
    - [ ] Return validation status (adapter validation results)
  
  - [ ] `POST /api/iot-fuzzer/configuration/protocols/config/`
    - [ ] Save protocol configuration (Django model)
    - [ ] Validate configuration parameters via adapter
    - [ ] Test connectivity if requested via adapter
    - [ ] Return configuration ID and status (Django response)
  
  - [ ] `POST /api/iot-fuzzer/configuration/protocols/test-connection/`
    - [ ] Test protocol connection via adapter
    - [ ] Return connection status and diagnostics (adapter results)
    - [ ] Include performance metrics (adapter-sourced)

- [ ] **Generator Configuration Endpoints**
  - [ ] `GET /api/iot-fuzzer/configuration/generators/types/`
    - [ ] Return available generator types via adapter
    - [ ] Include generator-specific parameters (adapter capabilities)
    - [ ] Return supported mutation strategies (adapter features)
  
  - [ ] `GET /api/iot-fuzzer/configuration/generators/config/`
    - [ ] Return current generator configuration (Django model)
    - [ ] Include seed corpus and mutation settings
    - [ ] Return strategy parameters
  
  - [ ] `POST /api/iot-fuzzer/configuration/generators/config/`
    - [ ] Save generator configuration (Django model)
    - [ ] Validate generator parameters via adapter
    - [ ] Test generator functionality via adapter
    - [ ] Return configuration status (Django response)

- [ ] **Template Management Endpoints (Pure Django)**
  - [ ] `GET /api/iot-fuzzer/configuration/templates/list/`
    - [ ] Return available configuration templates (Django models)
    - [ ] Include template categories (Django data)
    - [ ] Return template usage statistics (Django-calculated)
  
  - [ ] `POST /api/iot-fuzzer/configuration/templates/load/`
    - [ ] Load selected template configuration (Django model)
    - [ ] Validate template compatibility via adapter
    - [ ] Return loaded configuration (Django JSON)
  
  - [ ] `POST /api/iot-fuzzer/configuration/templates/save/`
    - [ ] Save current configuration as template (Django model)
    - [ ] Validate template data (Django validation)
    - [ ] Return template ID and confirmation (Django response)

- [ ] **Configuration Validation (Adapter-based)**
  - [ ] `POST /api/iot-fuzzer/configuration/validate/`
    - [ ] Validate complete configuration via adapter
    - [ ] Check protocol compatibility via adapter
    - [ ] Test generator functionality via adapter
    - [ ] Return validation report (adapter results, Django-formatted)

### 3.3 Management Page Endpoints (Pure Django)
- [ ] **Test Group Management (Pure Django)**
  - [ ] `GET /api/iot-fuzzer/management/test-groups/list/`
    - [ ] Return all test groups with metadata (Django models)
    - [ ] Include test case counts and statistics (Django relationships)
    - [ ] Return group properties and settings (Django data)
  
  - [ ] `POST /api/iot-fuzzer/management/test-groups/create/`
    - [ ] Create new test group (Django model)
    - [ ] Validate group parameters (Django validation)
    - [ ] Return created group ID and details (Django response)
  
  - [ ] `PUT /api/iot-fuzzer/management/test-groups/update/{id}/`
    - [ ] Update test group properties (Django model)
    - [ ] Validate updated parameters (Django validation)
    - [ ] Return updated group details (Django response)
  
  - [ ] `DELETE /api/iot-fuzzer/management/test-groups/delete/{id}/`
    - [ ] Delete test group and associated test cases (Django cascade)
    - [ ] Handle cascade deletion properly (Django ORM)
    - [ ] Return deletion confirmation (Django response)
  
  - [ ] `POST /api/iot-fuzzer/management/test-groups/import/`
    - [ ] Import test groups from file (Django file handling)
    - [ ] Validate imported data (Django validation)
    - [ ] Return import status and statistics (Django response)

- [ ] **Test Case Management (Pure Django)**
  - [ ] `GET /api/iot-fuzzer/management/test-cases/list/`
    - [ ] Return test cases with group assignment (Django relationships)
    - [ ] Include protocol frame data (Django JSON fields)
    - [ ] Return execution statistics (Django-calculated)
  
  - [ ] `POST /api/iot-fuzzer/management/test-cases/create/`
    - [ ] Create new test case (Django model)
    - [ ] Validate protocol frame (Django + optional adapter validation)
    - [ ] Return created test case details (Django response)
  
  - [ ] `PUT /api/iot-fuzzer/management/test-cases/update/{id}/`
    - [ ] Update test case properties (Django model)
    - [ ] Validate protocol frame changes (Django + optional adapter validation)
    - [ ] Return updated test case details (Django response)
  
  - [ ] `DELETE /api/iot-fuzzer/management/test-cases/delete/{id}/`
    - [ ] Delete test case (Django model)
    - [ ] Clean up associated results (Django cascade)
    - [ ] Return deletion confirmation (Django response)
  
  - [ ] `POST /api/iot-fuzzer/management/test-cases/move/`
    - [ ] Move test case between groups (Django model update)
    - [ ] Validate group compatibility (Django validation)
    - [ ] Return move confirmation (Django response)

- [ ] **Protocol Frame Builder (Django with Optional Adapter Validation)**
  - [ ] `POST /api/iot-fuzzer/management/protocol-frames/build/`
    - [ ] Build protocol frame from field specifications (Django logic)
    - [ ] Validate field types and values (Django validation)
    - [ ] Optionally validate via adapter
    - [ ] Return built frame and hex preview (Django response)
  
  - [ ] `POST /api/iot-fuzzer/management/protocol-frames/validate/`
    - [ ] Validate protocol frame structure (Django + optional adapter)
    - [ ] Check field constraints (Django validation)
    - [ ] Return validation status and errors (Django response)
  
  - [ ] `GET /api/iot-fuzzer/management/protocol-frames/templates/`
    - [ ] Return protocol frame templates (Django data/config)
    - [ ] Include common frame patterns (Django templates)
    - [ ] Return template categories (Django organization)

- [ ] **Export/Import Functionality (Pure Django)**
  - [ ] `POST /api/iot-fuzzer/management/export/`
    - [ ] Export test groups and cases (Django models → file)
    - [ ] Support multiple export formats (Django serializers)
    - [ ] Return export file or download link (Django file handling)
  
  - [ ] `POST /api/iot-fuzzer/management/import/`
    - [ ] Import test groups and cases (file → Django models)
    - [ ] Validate imported data (Django validation)
    - [ ] Return import status and statistics (Django response)

### 3.4 Results Page Endpoints (Django with Adapter Data)
- [ ] **File Management (Django-managed)**
  - [ ] `GET /api/iot-fuzzer/results/files/tree/`
    - [ ] Return file tree structure (Django file system + database)
    - [ ] Include file types and metadata (Django-computed)
    - [ ] Return file sizes and timestamps (Django file stats)
  
  - [ ] `GET /api/iot-fuzzer/results/files/content/{id}/`
    - [ ] Return file content (Django file handling)
    - [ ] Handle different file types appropriately (Django logic)
    - [ ] Include file metadata (Django database)
  
  - [ ] `GET /api/iot-fuzzer/results/files/download/{id}/`
    - [ ] Download file (Django file response)
    - [ ] Set appropriate content type (Django headers)
    - [ ] Handle large files efficiently (Django streaming)

- [ ] **Log Management (Django-managed)**
  - [ ] `GET /api/iot-fuzzer/results/logs/list/`
    - [ ] Return test logs with filtering (Django models + queries)
    - [ ] Include log levels and categories (Django fields)
    - [ ] Return paginated results (Django pagination)
  
  - [ ] `POST /api/iot-fuzzer/results/logs/filter/`
    - [ ] Filter logs by criteria (Django queries)
    - [ ] Support search functionality (Django search)
    - [ ] Return filtered results (Django responses)
  
  - [ ] WebSocket for Live Logging (Django Channels)
    - [ ] Create `IoTFuzzerResultsConsumer` WebSocket consumer (Django-only)
    - [ ] Implement real-time log streaming (adapter events → WebSocket)
    - [ ] Add log filtering and buffering (Django logic)
    - [ ] Handle connection management (Django Channels)

- [ ] **Results Analysis (Django-computed)**
  - [ ] `GET /api/iot-fuzzer/results/analysis/summary/`
    - [ ] Return comprehensive result summary (Django aggregation)
    - [ ] Include statistical analysis (Django calculations)
    - [ ] Return performance metrics (Django + adapter data)
  
  - [ ] `GET /api/iot-fuzzer/results/analysis/charts/`
    - [ ] Return chart data for visualization (Django formatting)
    - [ ] Include time-series data (Django queries)
    - [ ] Return performance trends (Django analytics)
  
  - [ ] `POST /api/iot-fuzzer/results/analysis/export/`
    - [ ] Export results and analysis (Django export)
    - [ ] Support multiple export formats (Django serializers)
    - [ ] Return export file or download link (Django files)

- [ ] **Artifact Management (Django-managed with Adapter Data)**
  - [ ] `GET /api/iot-fuzzer/results/artifacts/`
    - [ ] Return crash artifacts and interesting findings (Django models)
    - [ ] Include artifact metadata (Django database)
    - [ ] Return artifact analysis (Django + adapter insights)

---

## ✅ Phase 4: Service Layer Implementation (Django-only with Adapter Pattern)

### 4.1 Fuzzer Manager Service (Django Service with Adapters)
- [ ] **Create FuzzerManager Class (Pure Django)**
  ```python
  class FuzzerManager:
      def __init__(self):
          self.active_campaigns = {}  # Django-managed
          self.orchestrator_adapters = {}  # Adapter instances
          self.monitor_adapters = {}  # Adapter instances
      
      def start_campaign(self, campaign_config):
          # Django: Validate and save campaign config
          # Django: Create adapter instances
          # Django: Start background task
          # Adapter: Initialize IoT Protocol Fuzzer components
          # Django: Return campaign ID
      
      def stop_campaign(self, campaign_id):
          # Adapter: Stop running campaign
          # Adapter: Cleanup fuzzer resources
          # Django: Update database
          # Django: Cleanup adapter instances
      
      def get_campaign_status(self, campaign_id):
          # Adapter: Get real-time status from fuzzer
          # Django: Merge with database state
          # Django: Return combined status
      
      def pause_campaign(self, campaign_id):
          # Adapter: Pause campaign execution
          # Django: Update database state
      
      def reset_campaign(self, campaign_id):
          # Django: Reset database state
          # Adapter: Reset fuzzer state
  ```

- [ ] **Integration with IoT Protocol Fuzzer (Adapter Classes)**
  - [ ] `OrchestratorAdapter` - wraps `iot_protocol_fuzzer.core.orchestrator.Orchestrator`
  - [ ] `MonitorAdapter` - wraps `iot_protocol_fuzzer.monitoring.monitor.Monitor`
  - [ ] `LoggerAdapter` - wraps `iot_protocol_fuzzer.analysis.logger.TestLogger`
  - [ ] All adapters are Django classes that import and use fuzzer components

- [ ] **Campaign Lifecycle Management (Django-managed)**
  - [ ] Campaign state management via Django models
  - [ ] Resource allocation and cleanup via adapters
  - [ ] Error handling and recovery in Django layer
  - [ ] Performance monitoring via Django + adapter data

- [ ] **Real-time Status Tracking (Django + Adapter)**
  - [ ] Statistics collection via adapters → Django aggregation
  - [ ] Progress tracking and estimation in Django
  - [ ] Anomaly detection via adapters → Django alerts
  - [ ] Performance metrics via adapters → Django storage

### 4.2 Configuration Manager Service (Django Service)
- [ ] **Create ConfigManager Class (Pure Django)**
  ```python
  class ConfigManager:
      def __init__(self):
          self.protocol_configs = {}  # Django cache
          self.generator_configs = {}  # Django cache
          self.template_cache = {}  # Django cache
          self.adapters = {}  # Adapter instances for validation
      
      def get_protocol_types(self):
          # Adapter: Query supported protocol types from fuzzer
          # Django: Format and return response
      
      def validate_protocol_config(self, config):
          # Django: Basic validation
          # Adapter: Fuzzer-specific validation
          # Django: Combine results
      
      def save_protocol_config(self, config):
          # Django: Save to database
          # Django: Update cache
          # Django: Return configuration ID
      
      def test_connection(self, config):
          # Adapter: Test connection via fuzzer
          # Django: Format results
  ```

- [ ] **Protocol Configuration Management (Django + Adapter)**
  - [ ] Support via adapters for CAN, UART, SPI, I2C, Ethernet, DoIP protocols
  - [ ] Device path detection via adapters → Django validation
  - [ ] Connection parameter validation via adapters
  - [ ] Protocol-specific settings managed in Django

- [ ] **Generator Configuration Management (Django + Adapter)**
  - [ ] Support via adapters for Radamsa, Custom, Genetic, Random generators
  - [ ] Seed corpus management in Django file system
  - [ ] Mutation strategy configuration in Django
  - [ ] Generator parameter validation via adapters

- [ ] **Template System (Pure Django)**
  - [ ] Template loading and saving via Django models
  - [ ] Template categorization in Django
  - [ ] Template validation via adapters when needed
  - [ ] Template usage tracking in Django

### 4.3 Test Manager Service (Pure Django)
- [ ] **Create TestManager Class (Pure Django)**
  ```python
  class TestManager:
      def __init__(self):
          self.test_groups = {}  # Django cache
          self.test_cases = {}  # Django cache
          self.protocol_builders = {}  # Django frame builders
      
      def create_test_group(self, group_config):
          # Django: Create and save group
          # Django: Validate configuration
          # Django: Return group ID
      
      def create_test_case(self, case_config):
          # Django: Create and save case
          # Django: Validate protocol frame
          # Optional Adapter: Validate frame with fuzzer
          # Django: Return case ID
      
      def build_protocol_frame(self, frame_spec):
          # Django: Build frame from specification
          # Django: Validate field types and values
          # Django: Return frame data and hex preview
      
      def validate_protocol_frame(self, frame_data):
          # Django: Basic validation
          # Optional Adapter: Fuzzer validation
          # Django: Return combined validation status
  ```

- [ ] **Test Group Management (Pure Django)**
  - [ ] Test group CRUD via Django models
  - [ ] Group properties stored in Django
  - [ ] Group-level statistics calculated in Django
  - [ ] Group import/export via Django serializers

- [ ] **Test Case Management (Pure Django)**
  - [ ] Test case CRUD via Django models
  - [ ] Protocol frame building in Django logic
  - [ ] Frame validation via Django + optional adapter
  - [ ] Test case execution tracking in Django

- [ ] **Protocol Frame Builder (Django + Optional Adapter)**
  - [ ] Visual frame construction in Django
  - [ ] Field type validation in Django
  - [ ] Frame template system in Django
  - [ ] Hex preview and validation in Django
  - [ ] Optional fuzzer validation via adapter

### 4.4 Result Manager Service (Django + Adapter)
- [ ] **Create ResultManager Class (Django + Adapter)**
  ```python
  class ResultManager:
      def __init__(self):
          self.result_cache = {}  # Django cache
          self.log_buffers = {}  # Django buffers
          self.artifact_storage = {}  # Django file management
      
      def process_result(self, result_data):
          # Adapter: Receive result from fuzzer
          # Django: Process and store in database
          # Django: Update statistics
      
      def get_result_summary(self, campaign_id):
          # Django: Query database for results
          # Django: Generate statistical analysis
          # Django: Return performance metrics
      
      def get_file_tree(self, campaign_id):
          # Django: Scan filesystem for result files
          # Django: Return tree with metadata
      
      def export_results(self, campaign_id, format):
          # Django: Query and serialize results
          # Django: Generate export file
          # Django: Return download link
  ```

- [ ] **Result Processing (Django + Adapter Events)**
  - [ ] Adapter: Capture results from fuzzer → Django event system
  - [ ] Django: Real-time processing and database storage
  - [ ] Django: Statistical analysis and aggregation
  - [ ] Django: Performance metrics calculation
  - [ ] Django: Anomaly detection and classification

- [ ] **File Management (Pure Django)**
  - [ ] Django: Result file organization and metadata
  - [ ] Django: Artifact storage and retrieval
  - [ ] Django: File tree generation and navigation
  - [ ] Django: Large file handling and optimization

- [ ] **Log Management (Django + Adapter Events)**
  - [ ] Adapter: Real-time log capture from fuzzer → Django
  - [ ] Django: Log collection and buffering
  - [ ] Django: Log filtering and search functionality
  - [ ] Django: Log level management and rotation

- [ ] **Export and Reporting (Pure Django)**
  - [ ] Django: Multiple export formats (JSON, CSV, PDF)
  - [ ] Django: Comprehensive report generation
  - [ ] Django: Chart data preparation
  - [ ] Django: Custom report templates

---

## ✅ Phase 5: Real-time Communication (Django-only)

### 5.1 WebSocket Implementation (Pure Django Channels)
- [ ] **Configure Django Channels**
  - [ ] Verify `channels` in requirements.txt
  - [ ] Update `sat_django_entry/settings.py` with Channels configuration
  - [ ] Create `sat_toolkit/routing.py` if not exists
  - [ ] Add IoT fuzzer WebSocket routes

- [ ] **Create WebSocket Consumers (Pure Django)**
  - [ ] Create `sat_toolkit/consumers/iot_fuzzer_consumer.py`
  - [ ] Implement `IoTFuzzerTestingConsumer` for testing page
  - [ ] Implement `IoTFuzzerResultsConsumer` for results page
  - [ ] Add connection handling and authentication (Django)

- [ ] **Real-time Data Broadcasting (Django + Adapter Events)**
  - [ ] Adapter events → Django event system → WebSocket broadcast
  - [ ] Campaign status updates via adapter events
  - [ ] Test execution progress via adapter events
  - [ ] Statistics and performance metrics (Django-calculated)
  - [ ] Crash alerts and anomaly notifications (adapter → Django)
  - [ ] Live log streaming (adapter → Django → WebSocket)

### 5.2 Background Tasks (Pure Django/Celery)
- [ ] **Create Celery Tasks (Pure Django)**
  - [ ] Create `sat_toolkit/tasks/iot_fuzzer_tasks.py`
  - [ ] Implement `run_fuzzing_campaign` task (Django task + adapter usage)
  - [ ] Implement `process_results` task (Django task)
  - [ ] Implement `generate_report` task (Django task)
  - [ ] Add task status monitoring (Django)

- [ ] **Task Management (Pure Django)**
  - [ ] Django: Task lifecycle management
  - [ ] Django: Error handling and recovery
  - [ ] Django: Task progress tracking
  - [ ] Django + Adapter: Resource cleanup

---

## ✅ Phase 6: Integration & Testing (Django-focused)

### 6.1 Django Integration
- [ ] **Update URL Configuration**
  - [ ] Add imports to `sat_toolkit/urls.py`
  - [ ] Add all IoT fuzzer URL patterns
  - [ ] Follow existing naming conventions
  - [ ] Test URL resolution

- [ ] **Update Settings**
  - [ ] Add IoT fuzzer Django apps if needed
  - [ ] Configure WebSocket settings
  - [ ] Add logging configuration
  - [ ] Configure static file handling

- [ ] **Database Migration**
  - [ ] Generate migration files
  - [ ] Review migration for correctness
  - [ ] Apply migration to database
  - [ ] Test model relationships

### 6.2 End-to-End Testing (Django + Adapter Integration)
- [ ] **API Endpoint Testing**
  - [ ] Test all Django endpoints with proper data
  - [ ] Verify Django error handling
  - [ ] Test Django authentication and authorization
  - [ ] Validate Django response formats
  - [ ] Test adapter integration points

- [ ] **WebSocket Testing (Django)**
  - [ ] Test Django WebSocket connections
  - [ ] Verify real-time data flow from adapters
  - [ ] Test Django connection handling
  - [ ] Validate Django message formats

- [ ] **Integration Testing (Django + Adapter)**
  - [ ] Test complete fuzzing workflow (Django orchestration + adapter execution)
  - [ ] Verify Django data persistence
  - [ ] Test Django background task execution
  - [ ] Validate Django file operations
  - [ ] Test adapter error handling → Django recovery

### 6.3 Flutter Integration (Django API)
- [ ] **Update Flutter API Services**
  - [ ] Update API endpoint URLs to Django endpoints
  - [ ] Add new Django API service methods
  - [ ] Implement Django WebSocket connections
  - [ ] Add Django error handling

- [ ] **Test Flutter-Django Communication**
  - [ ] Test all Django API endpoints from Flutter
  - [ ] Verify Django WebSocket functionality
  - [ ] Test real-time data updates via Django
  - [ ] Validate Django error handling in Flutter

---

## ✅ Phase 7: Advanced Features (Django-focused)

### 7.1 Security & Performance (Django)
- [ ] **Security Implementation (Django)**
  - [ ] Add Django API authentication
  - [ ] Implement Django permission system
  - [ ] Add Django rate limiting
  - [ ] Secure Django WebSocket connections

- [ ] **Performance Optimization (Django)**
  - [ ] Optimize Django database queries
  - [ ] Implement Django caching
  - [ ] Add Django pagination for large datasets
  - [ ] Optimize Django WebSocket message handling
  - [ ] Optimize adapter call patterns

### 7.2 Monitoring & Alerting (Django)
- [ ] **System Monitoring (Django)**
  - [ ] Add Django system health monitoring
  - [ ] Implement Django campaign alerts
  - [ ] Add Django performance metrics
  - [ ] Create Django diagnostic endpoints

- [ ] **Logging & Debugging (Django)**
  - [ ] Enhanced Django logging configuration
  - [ ] Django debug mode support
  - [ ] Django error tracking and reporting
  - [ ] Django performance profiling
  - [ ] Adapter error logging in Django

---

## 🚀 Implementation Priority

### **High Priority (MVP - Must Have)**
1. **Phase 1**: Django Architecture Setup with Adapter Pattern
2. **Phase 2**: Pure Django Data Models & Database
3. **Phase 3.1**: Testing Page Endpoints (Django + Adapters)
4. **Phase 4.1**: Django Fuzzer Manager with Adapters
5. **Phase 6.1**: Django Integration

### **Medium Priority (Core Features)**
1. **Phase 3.2-3.4**: Configuration, Management, Results Endpoints (Django)
2. **Phase 4.2-4.4**: Django Manager Services with Adapters
3. **Phase 5.1**: Django WebSocket Implementation
4. **Phase 6.2-6.3**: Testing and Flutter Integration

### **Low Priority (Advanced Features)**
1. **Phase 5.2**: Django Background Tasks
2. **Phase 7**: Django Advanced Features

---

## 📊 Success Criteria

### **MVP Success Criteria**
- [ ] Django IoT fuzzer endpoints accessible
- [ ] Fuzzing campaigns controllable via Django + adapters
- [ ] Test results stored in Django database
- [ ] Flutter UI communicates with Django backend only
- [ ] Real-time updates via Django WebSocket

### **Full Feature Success Criteria**
- [ ] All four Flutter UI pages work with Django backend
- [ ] Complete fuzzing workflow via Django + adapters
- [ ] Real-time monitoring via Django + adapter events
- [ ] Import/export via Django functionality
- [ ] Protocol frame builder in Django
- [ ] Template system in Django
- [ ] Django WebSocket real-time updates operational

### **Quality Criteria**
- [ ] All Django API endpoints have proper error handling
- [ ] Django database relationships properly maintained
- [ ] Django WebSocket connections stable
- [ ] Performance acceptable for Django use cases
- [ ] Django security measures in place
- [ ] Code follows existing Django project patterns
- [ ] Zero modifications to iot_protocol_fuzzer codebase

---

## 📝 Notes

### **Architecture Principles**
- **Zero Cross-Dependency**: iot_protocol_fuzzer remains completely independent
- **Adapter Pattern**: All integration via Django adapter classes
- **Event-Driven**: Fuzzer events bridge to Django events
- **Django-Centric**: All business logic, state management, and UI communication in Django
- **Clean Separation**: Clear boundaries between fuzzer functionality and Django integration

### **Technical Considerations**
- Follow existing Django project patterns and conventions
- Maintain Django compatibility with existing codebase
- Ensure proper Django error handling and logging
- Consider Django scalability for multiple concurrent campaigns
- Handle adapter/fuzzer dependencies gracefully in Django
- All fuzzer interaction via adapters only

### **Integration Points**
- Adapter classes bridge fuzzer components to Django
- Django WebSocket consumers handle real-time communication
- Django background tasks orchestrate fuzzer operations via adapters
- Django database models store all application state
- Django URL patterns maintain API consistency
- Adapters provide the only interface to iot_protocol_fuzzer

### **Testing Strategy**
- Unit tests for Django service classes and adapters
- Integration tests for Django API endpoints
- Django WebSocket functionality testing
- End-to-end workflow testing (Django + adapters)
- Performance testing for Django + adapter interactions
- Zero testing modifications to iot_protocol_fuzzer

This updated TODO list ensures complete architectural separation while maintaining full functionality through the adapter pattern. 