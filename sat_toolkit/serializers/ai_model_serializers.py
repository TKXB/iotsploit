from rest_framework import serializers
from ..models.AIModel_Model import AIModelConfig, AIModelTemplate, AIModelProvider

class AIModelConfigSerializer(serializers.ModelSerializer):
    """AI模型配置序列化器"""
    
    provider_display = serializers.CharField(source='get_provider_display', read_only=True)
    api_key_masked = serializers.SerializerMethodField()
    
    class Meta:
        model = AIModelConfig
        fields = [
            'id', 'name', 'provider', 'provider_display', 'model_name',
            'api_url', 'api_key_masked', 'extra_config', 'is_active',
            'is_default', 'created_at', 'updated_at', 'usage_count',
            'last_used_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'usage_count', 'last_used_at']
    
    def get_api_key_masked(self, obj):
        """返回掩码后的API密钥"""
        api_key = obj.get_api_key()
        if api_key:
            if len(api_key) > 8:
                return api_key[:4] + '*' * (len(api_key) - 8) + api_key[-4:]
            else:
                return '*' * len(api_key)
        return ''

class AIModelConfigCreateSerializer(serializers.ModelSerializer):
    """AI模型配置创建序列化器"""
    
    api_key = serializers.CharField(write_only=True, help_text="API密钥")
    
    class Meta:
        model = AIModelConfig
        fields = [
            'name', 'provider', 'model_name', 'api_url', 'api_key',
            'extra_config', 'is_active', 'is_default'
        ]
    
    def create(self, validated_data):
        api_key = validated_data.pop('api_key')
        config = AIModelConfig(**validated_data)
        config.set_api_key(api_key)
        config.save()
        return config

class AIModelConfigUpdateSerializer(serializers.ModelSerializer):
    """AI模型配置更新序列化器"""
    
    api_key = serializers.CharField(write_only=True, required=False, help_text="API密钥")
    
    class Meta:
        model = AIModelConfig
        fields = [
            'name', 'provider', 'model_name', 'api_url', 'api_key',
            'extra_config', 'is_active', 'is_default'
        ]
    
    def update(self, instance, validated_data):
        api_key = validated_data.pop('api_key', None)
        
        # 更新其他字段
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # 如果提供了新的API密钥，则更新
        if api_key:
            instance.set_api_key(api_key)
        
        instance.save()
        return instance

class AIModelTemplateSerializer(serializers.ModelSerializer):
    """AI模型模板序列化器"""
    
    provider_display = serializers.CharField(source='get_provider_display', read_only=True)
    
    class Meta:
        model = AIModelTemplate
        fields = [
            'id', 'provider', 'provider_display', 'default_api_url',
            'supported_models', 'default_config', 'required_fields',
            'documentation_url'
        ]

class AIModelProviderSerializer(serializers.Serializer):
    """AI模型提供商序列化器"""
    
    value = serializers.CharField()
    label = serializers.CharField()
    default_url = serializers.URLField()
    supported_models = serializers.ListField(child=serializers.CharField())
    required_fields = serializers.ListField(child=serializers.CharField())
    documentation_url = serializers.URLField()

class AIModelTestConnectionSerializer(serializers.Serializer):
    """AI模型连接测试序列化器"""
    
    success = serializers.BooleanField()
    message = serializers.CharField()
    response_time = serializers.FloatField()

class AIModelCreateFromTemplateSerializer(serializers.Serializer):
    """从模板创建AI模型配置序列化器"""
    
    provider = serializers.ChoiceField(choices=AIModelProvider.choices)
    name = serializers.CharField(max_length=100)
    api_key = serializers.CharField()
    model_name = serializers.CharField(max_length=100)
    custom_config = serializers.JSONField(default=dict, required=False)
    
    def validate_name(self, value):
        """验证配置名称唯一性"""
        if AIModelConfig.objects.filter(name=value).exists():
            raise serializers.ValidationError("配置名称已存在")
        return value 