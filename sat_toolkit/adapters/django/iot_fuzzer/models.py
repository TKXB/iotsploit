"""
IoT Fuzzer Django Models (Adapter Layer)

NOTE:
- This module is Django-specific infrastructure (ORM + admin classes).
- It is intentionally placed under `sat_toolkit.adapters.django.*` to respect
  Ports & Adapters boundaries (core must not depend on it).
- The app label remains `sat_toolkit` because this module lives under the
  `sat_toolkit` package which is in INSTALLED_APPS, so existing migrations keep working.
"""

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

import logging

logger = logging.getLogger(__name__)


class FuzzingCampaign(models.Model):
    """
    Fuzzing Campaign Model - Manages overall fuzzing campaigns
    """

    STATUS_CHOICES = [
        ("idle", "Idle"),
        ("running", "Running"),
        ("paused", "Paused"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    name = models.CharField(max_length=255, help_text="Campaign name")
    description = models.TextField(blank=True, help_text="Campaign description")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="idle", help_text="Campaign status"
    )

    # Configuration
    protocol_type = models.CharField(max_length=50, help_text="Primary protocol type for this campaign")
    protocol_config = models.JSONField(default=dict, help_text="Protocol-specific configuration")
    generator_config = models.JSONField(default=dict, help_text="Test generation configuration")
    monitoring_config = models.JSONField(default=dict, help_text="Monitoring and logging configuration")

    # Timing
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(default=0.0)

    # Statistics
    total_iterations = models.IntegerField(default=0)
    total_cases = models.IntegerField(default=0)
    passed_cases = models.IntegerField(default=0)
    failed_cases = models.IntegerField(default=0)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    # Runtime UUID (stable across services), complementary to integer PK
    campaign_uuid = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        help_text="Runtime UUID for this campaign",
    )

    # Fuzzer integration
    fuzzer_instance_id = models.CharField(
        max_length=100, null=True, blank=True, help_text="Reference to fuzzer instance"
    )

    class Meta:
        db_table = "iot_fuzzing_campaigns"
        verbose_name = "IoT Fuzzing Campaign"
        verbose_name_plural = "IoT Fuzzing Campaigns"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[Campaign:{self.pk} {self.name}]"

    def get_progress_percentage(self):
        """Calculate campaign progress percentage"""
        if self.total_cases == 0:
            return 0
        completed = self.passed_cases + self.failed_cases
        return (completed / self.total_cases) * 100

    def can_start(self):
        """Check if campaign can be started"""
        return self.status in ["idle", "paused"]

    def can_pause(self):
        """Check if campaign can be paused"""
        return self.status == "running"

    def can_stop(self):
        """Check if campaign can be stopped"""
        return self.status in ["running", "paused"]


class TestGroup(models.Model):
    """
    Test Group Model - Organizes test cases into logical groups
    """

    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("normal", "Normal"),
        ("high", "High"),
        ("critical", "Critical"),
    ]

    name = models.CharField(max_length=255, help_text="Test group name")
    description = models.TextField(blank=True, help_text="Test group description")
    campaign = models.ForeignKey(
        FuzzingCampaign,
        on_delete=models.CASCADE,
        related_name="test_groups",
        null=True,
        blank=True,
        help_text="Associated campaign (optional)",
    )
    priority = models.CharField(
        max_length=20, choices=PRIORITY_CHOICES, default="normal", help_text="Test group priority"
    )
    enabled = models.BooleanField(default=True, help_text="Whether this group is enabled")
    created_at = models.DateTimeField(auto_now_add=True)

    # Group properties
    protocol_type = models.CharField(max_length=50, help_text="Protocol type for this group")

    # Statistics (calculated from test cases)
    total_cases = models.IntegerField(default=0, help_text="Total test cases in group")
    completed_cases = models.IntegerField(default=0, help_text="Completed test cases")
    failed_cases = models.IntegerField(default=0, help_text="Failed test cases")

    class Meta:
        db_table = "iot_test_groups"
        verbose_name = "IoT Test Group"
        verbose_name_plural = "IoT Test Groups"
        ordering = ["priority", "name"]
        indexes = [
            models.Index(fields=["enabled", "priority"]),
            models.Index(fields=["protocol_type"]),
            models.Index(fields=["campaign"]),
        ]

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
        self.failed_cases = test_cases.filter(last_result="failed").count()
        self.save()

    def get_enabled_test_cases_with_rules(self):
        """
        Get enabled test cases with their fuzzing rules and frame fields
        Optimized query using prefetch_related and select_related
        """
        return (
            self.test_cases.filter(enabled=True)
            .select_related("protocol_config", "group")
            .prefetch_related("frame_fields", "fuzzing_rules__target_field", "fuzzing_rules")
            .order_by("priority", "name")
        )


class ProtocolConfiguration(models.Model):
    """
    Protocol Configuration Model - Stores protocol-specific settings
    """

    PROTOCOL_TYPE_CHOICES = [
        ("can", "CAN Bus"),
        ("uart", "UART/Serial"),
        ("spi", "SPI"),
        ("i2c", "I2C"),
        ("ethernet", "Ethernet"),
        ("doip", "DoIP"),
    ]

    protocol_type = models.CharField(max_length=20, choices=PROTOCOL_TYPE_CHOICES, help_text="Protocol type")

    # Protocol-specific settings (JSON)
    settings = models.JSONField(default=dict, help_text="Protocol-specific configuration settings")

    class Meta:
        db_table = "iot_protocol_configurations"
        verbose_name = "Protocol Configuration"
        verbose_name_plural = "Protocol Configurations"

    def __str__(self):
        return f"[ProtocolConfig:{self.pk} {self.protocol_type}]"


class IoTConfiguration(models.Model):
    """
    IoT Configuration Model - Stores complete IoT Fuzzer configuration
    """

    name = models.CharField(max_length=255, help_text="Configuration name")
    description = models.TextField(blank=True, help_text="Configuration description")

    # Protocol Configuration
    protocol_type = models.CharField(
        max_length=20,
        choices=ProtocolConfiguration.PROTOCOL_TYPE_CHOICES,
        help_text="Protocol type",
    )
    protocol_settings = models.JSONField(default=dict, help_text="Protocol-specific settings")

    # Fuzzing Engine Configuration
    generator_type = models.CharField(
        max_length=50, default="radamsa", help_text="Fuzzing generator type"
    )
    generator_settings = models.JSONField(default=dict, help_text="Generator-specific settings")

    # Test Campaign Configuration
    campaign_settings = models.JSONField(default=dict, help_text="Test campaign settings")

    # Monitoring Configuration
    monitoring_settings = models.JSONField(default=dict, help_text="Monitoring and logging settings")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, help_text="Whether this configuration is active")

    class Meta:
        db_table = "iot_configurations"
        verbose_name = "IoT Configuration"
        verbose_name_plural = "IoT Configurations"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"[IoTConfig:{self.pk} {self.name}]"

    def get_protocol_display_name(self):
        """Get display name for protocol type"""
        for choice in ProtocolConfiguration.PROTOCOL_TYPE_CHOICES:
            if choice[0] == self.protocol_type:
                return choice[1]
        return self.protocol_type

    def to_dict(self):
        """Convert configuration to dictionary format"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "protocol_type": self.protocol_type,
            "protocol_settings": self.protocol_settings,
            "generator_type": self.generator_type,
            "generator_settings": self.generator_settings,
            "campaign_settings": self.campaign_settings,
            "monitoring_settings": self.monitoring_settings,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_active": self.is_active,
        }


class FrameField(models.Model):
    """
    Frame Field Model - Individual fields within a protocol frame
    """

    FIELD_TYPE_CHOICES = [
        ("hex", "Hexadecimal"),
        ("dec", "Decimal"),
        ("auto", "Auto-generated"),
        ("binary", "Binary"),
        ("string", "String"),
    ]

    test_case = models.ForeignKey(
        "TestCase", on_delete=models.CASCADE, related_name="frame_fields", help_text="Associated test case"
    )

    # Field definition
    field_name = models.CharField(max_length=100, help_text="Field name (user-editable)")
    field_id = models.CharField(max_length=100, help_text="Field identifier")
    field_type = models.CharField(
        max_length=20, choices=FIELD_TYPE_CHOICES, default="hex", help_text="Field data type"
    )

    # Field value and properties
    value = models.TextField(help_text="Field value")
    default_value = models.TextField(blank=True, help_text="Default field value")
    placeholder = models.CharField(max_length=255, blank=True, help_text="Placeholder text")
    is_required = models.BooleanField(default=False, help_text="Whether field is required")

    # Positioning and ordering
    field_order = models.IntegerField(default=0, help_text="Field order within frame")
    bit_offset = models.IntegerField(null=True, blank=True, help_text="Bit offset within frame")
    bit_length = models.IntegerField(null=True, blank=True, help_text="Field length in bits")

    # Bit-level fuzzing support
    target_bits = models.CharField(
        max_length=255, blank=True, help_text="Bit positions to fuzz (e.g., '0,1,7' or '0-7')"
    )

    class Meta:
        db_table = "iot_frame_fields"
        verbose_name = "Frame Field"
        verbose_name_plural = "Frame Fields"
        ordering = ["test_case", "field_order"]
        unique_together = ["test_case", "field_id"]
        indexes = [
            models.Index(fields=["test_case", "field_order"]),
            models.Index(fields=["field_type"]),
            models.Index(fields=["target_bits"]),
        ]

    def __str__(self):
        return f"[FrameField:{self.pk} {self.field_name}]"


class FuzzingRule(models.Model):
    """
    Fuzzing Rule Model - Defines how specific fields or bits should be fuzzed
    """

    FUZZING_STRATEGY_CHOICES = [
        ("random", "Random"),
        ("sequential", "Sequential"),
        ("pattern_based", "Pattern-based"),
        ("boundary", "Boundary Testing"),
        ("bit_flip", "Bit Flipping"),
        ("injection", "Injection"),
    ]

    TARGET_TYPE_CHOICES = [
        ("field", "Field-level"),
        ("bit", "Bit-level"),
        ("byte", "Byte-level"),
        ("frame", "Frame-level"),
    ]

    test_case = models.ForeignKey(
        "TestCase", on_delete=models.CASCADE, related_name="fuzzing_rules", help_text="Associated test case"
    )

    # Rule identification
    rule_name = models.CharField(max_length=100, help_text="Rule name")
    description = models.TextField(blank=True, help_text="Rule description")
    enabled = models.BooleanField(default=True, help_text="Whether rule is enabled")

    # Fuzzing target
    target_type = models.CharField(max_length=20, choices=TARGET_TYPE_CHOICES, help_text="Type of fuzzing target")
    target_field = models.ForeignKey(
        FrameField, on_delete=models.CASCADE, null=True, blank=True, help_text="Target field (for field-level fuzzing)"
    )

    # Bit-level targeting
    target_bits = models.CharField(
        max_length=255, blank=True, help_text="Bit positions to fuzz (e.g., '0,1,7' or '0-7')"
    )

    # Fuzzing strategy
    strategy = models.CharField(
        max_length=20, choices=FUZZING_STRATEGY_CHOICES, default="random", help_text="Fuzzing strategy to use"
    )

    # Strategy-specific configuration
    strategy_config = models.JSONField(default=dict, help_text="Strategy-specific configuration parameters")

    # Execution settings
    iterations_per_rule = models.IntegerField(default=100, help_text="Number of iterations for this rule")
    priority = models.IntegerField(default=50, help_text="Rule execution priority (0-100)")

    class Meta:
        db_table = "iot_fuzzing_rules"
        # Keep consistent with existing migrations/state to avoid generating new migrations
        verbose_name = "Fuzzing Rule"
        verbose_name_plural = "Fuzzing Rules"
        ordering = ["test_case", "-priority", "rule_name"]
        indexes = [
            models.Index(fields=["test_case", "enabled"]),
            models.Index(fields=["target_type"]),
            models.Index(fields=["strategy"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["target_bits"]),
        ]

    def __str__(self):
        return f"[FuzzingRule:{self.pk} {self.rule_name}]"

    @classmethod
    def get_bit_level_rules(cls, test_case_ids=None):
        """
        Get all bit-level fuzzing rules
        Optimized query for bit-level fuzzing operations
        """
        queryset = (
            cls.objects.filter(enabled=True, target_type="bit")
            .select_related("test_case", "target_field")
            .order_by("test_case", "-priority")
        )

        if test_case_ids:
            queryset = queryset.filter(test_case_id__in=test_case_ids)

        return queryset

    @classmethod
    def get_field_level_rules(cls, test_case_ids=None):
        """
        Get all field-level fuzzing rules
        Optimized query for field-level fuzzing operations
        """
        queryset = (
            cls.objects.filter(enabled=True, target_type="field")
            .select_related("test_case", "target_field")
            .order_by("test_case", "-priority")
        )

        if test_case_ids:
            queryset = queryset.filter(test_case_id__in=test_case_ids)

        return queryset


class TestCase(models.Model):
    """
    Redesigned Test Case Model - Comprehensive test case with fuzzing support
    """

    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("normal", "Normal"),
        ("high", "High"),
        ("critical", "Critical"),
    ]

    RESULT_CHOICES = [
        ("success", "Success"),
        ("failed", "Failed"),
        ("timeout", "Timeout"),
        ("error", "Error"),
        ("crash", "Crash"),
    ]

    # Basic Information
    name = models.CharField(max_length=255, help_text="Test case name")
    description = models.TextField(blank=True, help_text="Test case description")
    priority = models.CharField(
        max_length=20, choices=PRIORITY_CHOICES, default="normal", help_text="Test case priority"
    )
    enabled = models.BooleanField(default=True, help_text="Whether this test case is enabled")
    created_at = models.DateTimeField(default=timezone.now, help_text="Test case creation time")

    # Group Association
    group = models.ForeignKey(
        TestGroup,
        on_delete=models.CASCADE,
        related_name="test_cases",
        help_text="Associated test group",
    )

    # Protocol Configuration
    protocol_config = models.ForeignKey(
        ProtocolConfiguration, on_delete=models.CASCADE, help_text="Protocol configuration for this test case"
    )

    # Frame Definition (basic metadata - fields stored separately)
    frame_name = models.CharField(
        max_length=255, default="Protocol Frame", help_text="Name of the protocol frame"
    )
    frame_description = models.TextField(blank=True, help_text="Description of the protocol frame")

    # Execution Settings
    timeout_seconds = models.FloatField(default=5.0, help_text="Test timeout in seconds")
    iterations = models.IntegerField(default=100, help_text="Number of test iterations")
    expected_response = models.JSONField(null=True, blank=True, help_text="Expected response pattern")

    # Execution tracking
    execution_count = models.IntegerField(default=0, help_text="Number of times executed")
    last_executed = models.DateTimeField(null=True, blank=True, help_text="Last execution time")
    last_result = models.CharField(
        max_length=20, choices=RESULT_CHOICES, null=True, blank=True, help_text="Last execution result"
    )

    class Meta:
        db_table = "iot_test_cases"
        verbose_name = "IoT Test Case"
        verbose_name_plural = "IoT Test Cases"
        ordering = ["group", "priority", "name"]
        indexes = [
            models.Index(fields=["group", "enabled"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["enabled"]),
            models.Index(fields=["last_result"]),
            models.Index(fields=["protocol_config"]),
        ]

    def __str__(self):
        return f"[TestCase:{self.pk} {self.name}]"

    def clean(self):
        """Validate test case data"""
        if self.timeout_seconds <= 0:
            raise ValidationError("Timeout must be positive")
        if self.iterations <= 0:
            raise ValidationError("Iterations must be positive")

    def record_execution(self, result):
        """Record test execution"""
        self.execution_count += 1
        self.last_executed = timezone.now()
        self.last_result = result
        self.save()

    def get_frame_fields_ordered(self):
        """
        Get frame fields ordered by field_order
        Optimized query for frame field retrieval
        """
        return self.frame_fields.select_related("test_case").order_by("field_order")

    def get_frame_hex_output(self):
        """Get protocol frame as hex string from fields"""
        fields = self.get_frame_fields_ordered().filter(field_type__in=["hex", "dec"])

        hex_parts = []
        for field in fields:
            if field.value and field.value != "auto":
                # Convert field value to hex
                if field.field_type == "hex":
                    clean_hex = field.value.replace("0x", "").replace(" ", "")
                    if len(clean_hex) % 2 != 0:
                        clean_hex = "0" + clean_hex
                    hex_parts.append(clean_hex.upper())
                elif field.field_type == "dec":
                    try:
                        dec_val = int(field.value)
                        hex_val = f"{dec_val:02X}"
                        hex_parts.append(hex_val)
                    except ValueError:
                        continue

        return " ".join(hex_parts)

    def get_fuzzing_targets(self):
        """Get summary of fuzzing targets"""
        rules = self.fuzzing_rules.filter(enabled=True)
        field_targets = rules.filter(target_type="field").count()
        bit_targets = rules.filter(target_type="bit").count()

        return {"field_level": field_targets, "bit_level": bit_targets, "total_rules": rules.count()}


class FuzzingResult(models.Model):
    """
    Fuzzing Result Model - Records results from fuzzing execution
    """

    STATUS_CHOICES = [
        ("success", "Success"),
        ("crash", "Crash"),
        ("timeout", "Timeout"),
        ("error", "Error"),
        ("anomaly", "Anomaly"),
    ]

    campaign = models.ForeignKey(
        FuzzingCampaign, on_delete=models.CASCADE, related_name="results", help_text="Associated campaign"
    )
    test_case = models.ForeignKey(
        TestCase,
        on_delete=models.CASCADE,
        related_name="results",
        null=True,
        blank=True,
        help_text="Associated test case",
    )

    # Execution details
    iteration_number = models.IntegerField(help_text="Iteration number")
    executed_at = models.DateTimeField(auto_now_add=True, help_text="Execution timestamp")

    # Test payload
    payload_hex = models.TextField(help_text="Test payload in hex format")
    payload_size = models.IntegerField(help_text="Payload size in bytes")

    # Result details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, help_text="Execution result status")
    response_hex = models.TextField(blank=True, help_text="Response data in hex format")
    response_time_ms = models.FloatField(null=True, blank=True, help_text="Response time in milliseconds")

    # Crash information
    crashed = models.BooleanField(default=False, help_text="Whether execution crashed")
    crash_info = models.TextField(blank=True, help_text="Crash details and stack trace")

    # Artifact storage
    artifact_path = models.CharField(max_length=500, blank=True, help_text="Path to stored artifacts")

    class Meta:
        db_table = "iot_fuzzing_results"
        verbose_name = "IoT Fuzzing Result"
        verbose_name_plural = "IoT Fuzzing Results"
        ordering = ["-executed_at"]
        indexes = [
            models.Index(fields=["campaign", "test_case"]),
            models.Index(fields=["status"]),
            models.Index(fields=["executed_at"]),
        ]

    def __str__(self):
        return f"[Result:{self.pk} {self.status}]"

    def get_payload_preview(self, max_length=32):
        """Get truncated payload preview"""
        if len(self.payload_hex) <= max_length:
            return self.payload_hex
        return f"{self.payload_hex[:max_length]}..."

    def is_interesting(self):
        """Check if result is potentially interesting"""
        return self.status in ["crash", "anomaly", "timeout"]


class ConfigTemplate(models.Model):
    """
    Configuration Template Model - Stores reusable configurations
    """

    CATEGORY_CHOICES = [
        ("protocol", "Protocol Configuration"),
        ("generator", "Test Generator Configuration"),
        ("monitoring", "Monitoring Configuration"),
        ("complete", "Complete Campaign Configuration"),
    ]

    name = models.CharField(max_length=255, help_text="Template name")
    description = models.TextField(blank=True, help_text="Template description")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, help_text="Template category")

    # Configuration data
    protocol_config = models.JSONField(null=True, blank=True, help_text="Protocol configuration")
    generator_config = models.JSONField(null=True, blank=True, help_text="Generator configuration")
    monitoring_config = models.JSONField(null=True, blank=True, help_text="Monitoring configuration")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    is_default = models.BooleanField(default=False, help_text="Whether this is a default template")
    usage_count = models.IntegerField(default=0, help_text="Number of times used")

    class Meta:
        db_table = "iot_config_templates"
        verbose_name = "IoT Config Template"
        verbose_name_plural = "IoT Config Templates"
        ordering = ["-is_default", "-usage_count", "name"]

    def __str__(self):
        return f"[Template:{self.pk} {self.name}]"

    def increment_usage(self):
        """Increment usage counter"""
        self.usage_count += 1
        self.save(update_fields=["usage_count"])

    def get_full_config(self):
        """Get complete configuration dictionary"""
        return {"protocol": self.protocol_config or {}, "generator": self.generator_config or {}, "monitoring": self.monitoring_config or {}}


class LiveLog(models.Model):
    """
    Live Log Model - Stores real-time log entries
    """

    LEVEL_CHOICES = [
        ("debug", "Debug"),
        ("info", "Info"),
        ("warning", "Warning"),
        ("error", "Error"),
        ("critical", "Critical"),
    ]

    CATEGORY_CHOICES = [
        ("system", "System"),
        ("fuzzer", "Fuzzer"),
        ("protocol", "Protocol"),
        ("test", "Test Execution"),
        ("result", "Result Processing"),
    ]

    campaign = models.ForeignKey(
        FuzzingCampaign,
        on_delete=models.CASCADE,
        related_name="logs",
        null=True,
        blank=True,
        help_text="Associated campaign",
    )

    # Log details
    timestamp = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, help_text="Log level")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, help_text="Log category")
    source = models.CharField(max_length=100, help_text="Log source component")
    message = models.TextField(help_text="Log message")

    # Additional data
    extra_data = models.JSONField(null=True, blank=True, help_text="Additional structured data")

    class Meta:
        db_table = "iot_live_logs"
        verbose_name = "IoT Live Log"
        verbose_name_plural = "IoT Live Logs"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["campaign", "timestamp"]),
            models.Index(fields=["level"]),
            models.Index(fields=["category"]),
        ]

    def __str__(self):
        return f"[Log:{self.pk} {self.level} {self.source}]"

    def get_formatted_timestamp(self):
        """Get formatted timestamp string"""
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def is_error(self):
        """Check if log entry is an error"""
        return self.level in ["error", "critical"]


# -------------------- Admin configurations (still Django adapter) --------------------


class FuzzingCampaignAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "status", "protocol_type", "total_cases", "created_at"]
    list_filter = ["status", "protocol_type"]
    search_fields = ["name", "description"]
    readonly_fields = ["created_at", "started_at", "completed_at"]


class TestGroupAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "campaign", "priority", "enabled", "total_cases"]
    list_filter = ["priority", "enabled", "protocol_type"]
    search_fields = ["name", "description"]


class ProtocolConfigurationAdmin(admin.ModelAdmin):
    list_display = ["id", "protocol_type"]
    list_filter = ["protocol_type"]


class FrameFieldAdmin(admin.ModelAdmin):
    list_display = ["id", "field_name", "test_case", "field_type", "field_order"]
    list_filter = ["field_type", "is_required"]
    search_fields = ["field_name", "field_id"]
    ordering = ["test_case", "field_order"]


class FuzzingRuleAdmin(admin.ModelAdmin):
    list_display = ["id", "rule_name", "test_case", "target_type", "strategy", "enabled"]
    list_filter = ["target_type", "strategy", "enabled"]
    search_fields = ["rule_name", "description"]
    ordering = ["test_case", "-priority"]


class TestCaseAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "group", "priority", "enabled", "execution_count", "last_result"]
    list_filter = ["priority", "enabled", "last_result"]
    search_fields = ["name", "description"]
    readonly_fields = ["created_at", "last_executed", "execution_count"]


class FuzzingResultAdmin(admin.ModelAdmin):
    list_display = ["id", "campaign", "test_case", "status", "executed_at"]
    list_filter = ["status", "crashed"]
    search_fields = ["payload_hex", "response_hex"]
    readonly_fields = ["executed_at"]


class ConfigTemplateAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "category", "is_default", "usage_count", "created_at"]
    list_filter = ["category", "is_default"]
    search_fields = ["name", "description"]
    readonly_fields = ["created_at", "usage_count"]


class IoTConfigurationAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "protocol_type", "generator_type", "is_active", "updated_at"]
    list_filter = ["protocol_type", "generator_type", "is_active"]
    search_fields = ["name", "description"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        ("Basic Information", {"fields": ("name", "description", "is_active")}),
        ("Protocol Configuration", {"fields": ("protocol_type", "protocol_settings")}),
        ("Fuzzing Engine", {"fields": ("generator_type", "generator_settings")}),
        ("Test Campaign", {"fields": ("campaign_settings",)}),
        ("Monitoring", {"fields": ("monitoring_settings",)}),
        ("Metadata", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


class LiveLogAdmin(admin.ModelAdmin):
    list_display = ["id", "timestamp", "level", "category", "source", "message"]
    list_filter = ["level", "category", "source"]
    search_fields = ["message", "source"]
    readonly_fields = ["timestamp"]


