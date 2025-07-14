from django.db import models
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils import timezone
import json
import logging

logger = logging.getLogger(__name__)

class FuzzingCampaign(models.Model):
    """
    Fuzzing Campaign Model - Pure Django
    Manages fuzzing campaign lifecycle and configuration
    """
    
    STATUS_CHOICES = [
        ('idle', 'Idle'),
        ('preparing', 'Preparing'),
        ('running', 'Running'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    PROTOCOL_CHOICES = [
        ('can', 'CAN'),
        ('uart', 'UART'),
        ('spi', 'SPI'),
        ('ethernet', 'Ethernet'),
        ('doip', 'DoIP'),
    ]
    
    # Campaign identification
    name = models.CharField(max_length=255, help_text="Campaign name")
    description = models.TextField(blank=True, help_text="Campaign description")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Campaign configuration (JSON - no fuzzer coupling)
    protocol_type = models.CharField(
        max_length=50, 
        choices=PROTOCOL_CHOICES,
        help_text="Protocol type for fuzzing"
    )
    protocol_config = models.JSONField(
        default=dict,
        help_text="Protocol-specific configuration"
    )
    generator_config = models.JSONField(
        default=dict,
        help_text="Generator configuration parameters"
    )
    monitoring_config = models.JSONField(
        default=dict,
        help_text="Monitoring configuration parameters"
    )
    
    # Campaign state (Django-managed)
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES,
        default='idle',
        help_text="Current campaign status"
    )
    iterations_total = models.IntegerField(
        default=0,
        help_text="Total iterations planned"
    )
    iterations_completed = models.IntegerField(
        default=0,
        help_text="Iterations completed"
    )
    
    # Results summary (Django-calculated)
    crashes_found = models.IntegerField(
        default=0,
        help_text="Number of crashes found"
    )
    timeouts_occurred = models.IntegerField(
        default=0,
        help_text="Number of timeouts occurred"
    )
    errors_encountered = models.IntegerField(
        default=0,
        help_text="Number of errors encountered"
    )
    
    # Timing information (Django-managed)
    started_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Campaign start time"
    )
    completed_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Campaign completion time"
    )
    duration_seconds = models.IntegerField(
        default=0,
        help_text="Campaign duration in seconds"
    )
    
    # Adapter instance tracking (Django-internal)
    fuzzer_instance_id = models.CharField(
        max_length=100, 
        blank=True,
        help_text="Fuzzer instance identifier"
    )
    
    class Meta:
        db_table = 'iot_fuzzing_campaigns'
        verbose_name = 'IoT Fuzzing Campaign'
        verbose_name_plural = 'IoT Fuzzing Campaigns'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"[Campaign:{self.pk} {self.name}]"
    
    def clean(self):
        """Validate model data"""
        if self.iterations_completed > self.iterations_total:
            raise ValidationError("Completed iterations cannot exceed total iterations")
    
    def get_progress_percentage(self):
        """Calculate completion percentage"""
        if self.iterations_total == 0:
            return 0
        return (self.iterations_completed / self.iterations_total) * 100
    
    def get_duration_formatted(self):
        """Get formatted duration"""
        if self.duration_seconds == 0:
            return "0s"
        
        hours = self.duration_seconds // 3600
        minutes = (self.duration_seconds % 3600) // 60
        seconds = self.duration_seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    def is_active(self):
        """Check if campaign is currently active"""
        return self.status in ['preparing', 'running']
    
    def can_start(self):
        """Check if campaign can be started"""
        return self.status in ['idle', 'failed', 'cancelled']
    
    def can_pause(self):
        """Check if campaign can be paused"""
        return self.status == 'running'
    
    def can_resume(self):
        """Check if campaign can be resumed"""
        return self.status == 'paused'


class TestGroup(models.Model):
    """
    Test Group Model - Pure Django
    Organizes test cases into logical groups
    """
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    MUTATION_STRATEGY_CHOICES = [
        ('random', 'Random'),
        ('radamsa', 'Radamsa'),
        ('genetic', 'Genetic'),
        ('structured', 'Structured'),
        ('custom', 'Custom'),
    ]
    
    name = models.CharField(max_length=255, help_text="Test group name")
    description = models.TextField(blank=True, help_text="Test group description")
    campaign = models.ForeignKey(
        FuzzingCampaign, 
        on_delete=models.CASCADE,
        related_name='test_groups',
        help_text="Associated campaign"
    )
    priority = models.CharField(
        max_length=20, 
        choices=PRIORITY_CHOICES,
        default='normal',
        help_text="Test group priority"
    )
    enabled = models.BooleanField(
        default=True,
        help_text="Whether this group is enabled"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Group properties (Django-managed)
    protocol_type = models.CharField(
        max_length=50,
        help_text="Protocol type for this group"
    )
    mutation_strategy = models.CharField(
        max_length=50,
        choices=MUTATION_STRATEGY_CHOICES,
        default='random',
        help_text="Mutation strategy to use"
    )
    
    # Statistics (Django-calculated)
    total_cases = models.IntegerField(
        default=0,
        help_text="Total test cases in group"
    )
    completed_cases = models.IntegerField(
        default=0,
        help_text="Completed test cases"
    )
    failed_cases = models.IntegerField(
        default=0,
        help_text="Failed test cases"
    )
    
    class Meta:
        db_table = 'iot_test_groups'
        verbose_name = 'IoT Test Group'
        verbose_name_plural = 'IoT Test Groups'
        ordering = ['priority', 'name']
    
    def __str__(self):
        return f"[TestGroup:{self.pk} {self.name}]"
    
    def get_completion_percentage(self):
        """Calculate group completion percentage"""
        if self.total_cases == 0:
            return 0
        return (self.completed_cases / self.total_cases) * 100
    
    def update_statistics(self):
        """Update group statistics from test cases"""
        test_cases = self.test_cases.all()
        self.total_cases = test_cases.count()
        self.completed_cases = test_cases.filter(last_result__isnull=False).count()
        self.failed_cases = test_cases.filter(last_result='failed').count()
        self.save()


class TestCase(models.Model):
    """
    Test Case Model - Pure Django
    Individual test cases with protocol frames
    """
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    RESULT_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('timeout', 'Timeout'),
        ('error', 'Error'),
        ('crash', 'Crash'),
    ]
    
    name = models.CharField(max_length=255, help_text="Test case name")
    description = models.TextField(blank=True, help_text="Test case description")
    group = models.ForeignKey(
        TestGroup, 
        on_delete=models.CASCADE,
        related_name='test_cases',
        help_text="Associated test group"
    )
    
    # Test case configuration (JSON format - no fuzzer coupling)
    protocol_frame = models.JSONField(
        default=dict,
        help_text="Protocol frame configuration"
    )
    expected_response = models.JSONField(
        null=True, 
        blank=True,
        help_text="Expected response pattern"
    )
    timeout_seconds = models.FloatField(
        default=1.0,
        help_text="Test timeout in seconds"
    )
    
    # Test case properties (Django-managed)
    priority = models.CharField(
        max_length=20, 
        choices=PRIORITY_CHOICES,
        default='normal',
        help_text="Test case priority"
    )
    enabled = models.BooleanField(
        default=True,
        help_text="Whether this test case is enabled"
    )
    
    # Metadata
    created_at = models.DateTimeField(
        default=timezone.now,
        help_text="Test case creation time"
    )
    
    # Execution tracking (Django-managed)
    execution_count = models.IntegerField(
        default=0,
        help_text="Number of times executed"
    )
    last_executed = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Last execution time"
    )
    last_result = models.CharField(
        max_length=20, 
        choices=RESULT_CHOICES,
        null=True, 
        blank=True,
        help_text="Last execution result"
    )
    
    class Meta:
        db_table = 'iot_test_cases'
        verbose_name = 'IoT Test Case'
        verbose_name_plural = 'IoT Test Cases'
        ordering = ['priority', 'name']
    
    def __str__(self):
        return f"[TestCase:{self.pk} {self.name}]"
    
    def clean(self):
        """Validate test case data"""
        if self.timeout_seconds <= 0:
            raise ValidationError("Timeout must be positive")
    
    def record_execution(self, result):
        """Record test execution"""
        self.execution_count += 1
        self.last_executed = timezone.now()
        self.last_result = result
        self.save()
    
    def get_protocol_frame_hex(self):
        """Get protocol frame as hex string"""
        frame_data = self.protocol_frame.get('data', [])
        if isinstance(frame_data, list):
            return ''.join(f'{b:02x}' for b in frame_data)
        return str(frame_data)


class FuzzingResult(models.Model):
    """
    Fuzzing Result Model - Pure Django
    Records results from fuzzing execution
    """
    
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('crash', 'Crash'),
        ('timeout', 'Timeout'),
        ('error', 'Error'),
        ('anomaly', 'Anomaly'),
    ]
    
    campaign = models.ForeignKey(
        FuzzingCampaign, 
        on_delete=models.CASCADE,
        related_name='results',
        help_text="Associated campaign"
    )
    test_case = models.ForeignKey(
        TestCase, 
        on_delete=models.CASCADE,
        related_name='results',
        null=True, 
        blank=True,
        help_text="Associated test case"
    )
    
    # Execution details (Django-captured)
    iteration_number = models.IntegerField(help_text="Iteration number")
    executed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Execution timestamp"
    )
    
    # Test payload (from fuzzer via adapter)
    payload_hex = models.TextField(help_text="Test payload in hex format")
    payload_size = models.IntegerField(help_text="Payload size in bytes")
    
    # Result details (from fuzzer via adapter)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        help_text="Execution result status"
    )
    response_hex = models.TextField(
        blank=True,
        help_text="Response data in hex format"
    )
    response_time_ms = models.FloatField(
        null=True, 
        blank=True,
        help_text="Response time in milliseconds"
    )
    
    # Crash information (from fuzzer via adapter)
    crashed = models.BooleanField(
        default=False,
        help_text="Whether execution crashed"
    )
    crash_info = models.TextField(
        blank=True,
        help_text="Crash details and stack trace"
    )
    
    # Artifact storage (Django-managed)
    artifact_path = models.CharField(
        max_length=500, 
        blank=True,
        help_text="Path to stored artifacts"
    )
    
    class Meta:
        db_table = 'iot_fuzzing_results'
        verbose_name = 'IoT Fuzzing Result'
        verbose_name_plural = 'IoT Fuzzing Results'
        ordering = ['-executed_at']
        indexes = [
            models.Index(fields=['campaign', 'iteration_number']),
            models.Index(fields=['status']),
            models.Index(fields=['crashed']),
        ]
    
    def __str__(self):
        return f"[Result:{self.pk} Campaign:{self.campaign.name} Iter:{self.iteration_number}]"
    
    def get_payload_preview(self, length=32):
        """Get truncated payload preview"""
        if len(self.payload_hex) <= length:
            return self.payload_hex
        return self.payload_hex[:length] + '...'
    
    def has_response(self):
        """Check if result has response data"""
        return bool(self.response_hex)
    
    def is_interesting(self):
        """Check if result is interesting (crash or anomaly)"""
        return self.status in ['crash', 'anomaly'] or self.crashed


class ConfigTemplate(models.Model):
    """
    Configuration Template Model - Pure Django
    Reusable configuration templates
    """
    
    CATEGORY_CHOICES = [
        ('automotive', 'Automotive'),
        ('iot', 'IoT'),
        ('industrial', 'Industrial'),
        ('custom', 'Custom'),
    ]
    
    name = models.CharField(max_length=255, help_text="Template name")
    description = models.TextField(blank=True, help_text="Template description")
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default='custom',
        help_text="Template category"
    )
    
    # Template configuration (JSON format - adapter will convert)
    protocol_config = models.JSONField(
        default=dict,
        help_text="Protocol configuration template"
    )
    generator_config = models.JSONField(
        default=dict,
        help_text="Generator configuration template"
    )
    monitoring_config = models.JSONField(
        default=dict,
        help_text="Monitoring configuration template"
    )
    
    # Template metadata (Django-managed)
    created_at = models.DateTimeField(auto_now_add=True)
    is_default = models.BooleanField(
        default=False,
        help_text="Whether this is a default template"
    )
    usage_count = models.IntegerField(
        default=0,
        help_text="Number of times used"
    )
    
    class Meta:
        db_table = 'iot_config_templates'
        verbose_name = 'IoT Config Template'
        verbose_name_plural = 'IoT Config Templates'
        ordering = ['-is_default', 'category', 'name']
    
    def __str__(self):
        return f"[Template:{self.pk} {self.name}]"
    
    def increment_usage(self):
        """Increment usage counter"""
        self.usage_count += 1
        self.save()
    
    def get_full_config(self):
        """Get complete configuration"""
        return {
            'protocol_config': self.protocol_config,
            'generator_config': self.generator_config,
            'monitoring_config': self.monitoring_config
        }


class LiveLog(models.Model):
    """
    Live Log Model - Pure Django
    Real-time logging during fuzzing
    """
    
    LEVEL_CHOICES = [
        ('debug', 'Debug'),
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('critical', 'Critical'),
    ]
    
    CATEGORY_CHOICES = [
        ('fuzzer', 'Fuzzer'),
        ('protocol', 'Protocol'),
        ('system', 'System'),
        ('adapter', 'Adapter'),
        ('campaign', 'Campaign'),
    ]
    
    campaign = models.ForeignKey(
        FuzzingCampaign, 
        on_delete=models.CASCADE,
        related_name='logs',
        help_text="Associated campaign"
    )
    
    # Log entry details (Django-managed)
    timestamp = models.DateTimeField(
        auto_now_add=True,
        help_text="Log entry timestamp"
    )
    log_level = models.CharField(
        max_length=20,
        choices=LEVEL_CHOICES,
        default='info',
        help_text="Log level"
    )
    message = models.TextField(help_text="Log message")
    
    # Log categorization (Django-assigned)
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default='fuzzer',
        help_text="Log category"
    )
    source = models.CharField(
        max_length=100,
        help_text="Log source component"
    )
    
    # Additional data (from fuzzer via adapter)
    extra_data = models.JSONField(
        null=True, 
        blank=True,
        help_text="Additional log data"
    )
    
    class Meta:
        db_table = 'iot_live_logs'
        verbose_name = 'IoT Live Log'
        verbose_name_plural = 'IoT Live Logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['campaign', 'timestamp']),
            models.Index(fields=['log_level']),
            models.Index(fields=['category']),
        ]
    
    def __str__(self):
        return f"[Log:{self.pk} {self.log_level.upper()}] {self.message[:50]}..."
    
    def get_formatted_timestamp(self):
        """Get formatted timestamp"""
        return self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    
    def is_error(self):
        """Check if log entry is error level"""
        return self.log_level in ['error', 'critical']


# Admin Configuration
class FuzzingCampaignAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'protocol_type', 'status', 'progress', 'created_at']
    list_filter = ['status', 'protocol_type', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at', 'fuzzer_instance_id']
    
    def progress(self, obj):
        return f"{obj.get_progress_percentage():.1f}%"
    progress.short_description = 'Progress'


class TestGroupAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'campaign', 'priority', 'enabled', 'total_cases']
    list_filter = ['priority', 'enabled', 'protocol_type', 'mutation_strategy']
    search_fields = ['name', 'description']


class TestCaseAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'group', 'priority', 'enabled', 'execution_count', 'last_result']
    list_filter = ['priority', 'enabled', 'last_result']
    search_fields = ['name', 'description']


class FuzzingResultAdmin(admin.ModelAdmin):
    list_display = ['id', 'campaign', 'iteration_number', 'status', 'crashed', 'executed_at']
    list_filter = ['status', 'crashed', 'executed_at']
    search_fields = ['campaign__name']
    readonly_fields = ['executed_at']


class ConfigTemplateAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'category', 'is_default', 'usage_count', 'created_at']
    list_filter = ['category', 'is_default', 'created_at']
    search_fields = ['name', 'description']


class LiveLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'campaign', 'log_level', 'category', 'message_preview', 'timestamp']
    list_filter = ['log_level', 'category', 'timestamp']
    search_fields = ['message', 'source']
    readonly_fields = ['timestamp']
    
    def message_preview(self, obj):
        return obj.message[:100] + '...' if len(obj.message) > 100 else obj.message
    message_preview.short_description = 'Message' 