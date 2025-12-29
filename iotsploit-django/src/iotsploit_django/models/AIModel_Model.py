from django.db import models
from django.core.exceptions import ValidationError
import json
from cryptography.fernet import Fernet
from django.conf import settings
import base64

class AIModelProvider(models.TextChoices):
    """AI模型提供商选择"""
    OPENAI = 'openai', 'OpenAI'
    GOOGLE = 'google', 'Google (Gemini)'
    ANTHROPIC = 'anthropic', 'Anthropic (Claude)'
    AZURE_OPENAI = 'azure_openai', 'Azure OpenAI'
    OLLAMA = 'ollama', 'Ollama (Local)'
    CUSTOM = 'custom', 'Custom API'

class AIModelConfig(models.Model):
    """AI模型配置"""
    
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="配置名称，用于标识不同的AI模型配置"
    )
    
    provider = models.CharField(
        max_length=20,
        choices=AIModelProvider.choices,
        help_text="AI模型提供商"
    )
    
    model_name = models.CharField(
        max_length=100,
        help_text="具体的模型名称，如 gpt-4, claude-3-sonnet 等"
    )
    
    api_url = models.URLField(
        help_text="API端点URL"
    )
    
    api_key_encrypted = models.TextField(
        help_text="加密存储的API密钥"
    )
    
    # 额外配置参数
    extra_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="额外的配置参数，如温度、最大token等"
    )
    
    # 状态和元数据
    is_active = models.BooleanField(
        default=True,
        help_text="是否启用此配置"
    )
    
    is_default = models.BooleanField(
        default=False,
        help_text="是否为默认配置"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # 使用统计
    usage_count = models.IntegerField(
        default=0,
        help_text="使用次数统计"
    )
    
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="最后使用时间"
    )
    
    class Meta:
        db_table = 'ai_model_config'
        verbose_name = 'AI模型配置'
        verbose_name_plural = 'AI模型配置'
        ordering = ['-is_default', '-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.get_provider_display()})"
    
    @property
    def encryption_key(self):
        """获取加密密钥"""
        # 从Django设置中获取密钥，如果没有则生成一个
        if hasattr(settings, 'AI_MODEL_ENCRYPTION_KEY'):
            return settings.AI_MODEL_ENCRYPTION_KEY.encode()
        else:
            # 生成一个基于SECRET_KEY的固定密钥
            key_material = settings.SECRET_KEY[:32].ljust(32, '0')
            return base64.urlsafe_b64encode(key_material.encode())
    
    def set_api_key(self, api_key):
        """设置并加密API密钥"""
        if api_key:
            fernet = Fernet(self.encryption_key)
            encrypted_key = fernet.encrypt(api_key.encode())
            self.api_key_encrypted = base64.urlsafe_b64encode(encrypted_key).decode()
        else:
            self.api_key_encrypted = ''
    
    def get_api_key(self):
        """获取解密后的API密钥"""
        if not self.api_key_encrypted:
            return ''
        try:
            fernet = Fernet(self.encryption_key)
            encrypted_key = base64.urlsafe_b64decode(self.api_key_encrypted.encode())
            return fernet.decrypt(encrypted_key).decode()
        except Exception:
            return ''
    
    def get_masked_api_key(self):
        """获取掩码后的API密钥用于显示"""
        api_key = self.get_api_key()
        if not api_key:
            return ''
        if len(api_key) <= 8:
            return '*' * len(api_key)
        return api_key[:4] + '*' * (len(api_key) - 8) + api_key[-4:]
    
    def save(self, *args, **kwargs):
        # 确保只有一个默认配置 - 但只在完整保存时执行，不在部分字段更新时执行
        update_fields = kwargs.get('update_fields')
        if self.is_default and (update_fields is None or 'is_default' in update_fields):
            AIModelConfig.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        
        super().save(*args, **kwargs)
    
    def clean(self):
        """验证配置"""
        super().clean()
        
        # 验证URL格式
        if self.provider == AIModelProvider.OPENAI:
            if not self.api_url.startswith('https://api.openai.com'):
                if not self.api_url.startswith('https://'):
                    raise ValidationError({'api_url': 'OpenAI API URL必须使用HTTPS'})
        
        # 验证模型名称
        if self.provider == AIModelProvider.OPENAI:
            valid_models = ['gpt-4', 'gpt-4-turbo', 'gpt-3.5-turbo', 'gpt-4o', 'gpt-4o-mini']
            if not any(self.model_name.startswith(model) for model in valid_models):
                raise ValidationError({'model_name': f'不支持的OpenAI模型: {self.model_name}'})
    
    def test_connection(self):
        """测试API连接"""
        try:
            # 这里可以实现实际的API测试逻辑
            # 返回测试结果
            return {
                'success': True,
                'message': 'Connection test not implemented yet',
                'response_time': 0
            }
        except Exception as e:
            return {
                'success': False,
                'message': str(e),
                'response_time': 0
            }
    
    def get_config_dict(self):
        """获取配置字典，用于API调用"""
        config = {
            'provider': self.provider,
            'model_name': self.model_name,
            'api_url': self.api_url,
            'api_key': self.get_api_key(),
            **self.extra_config
        }
        return config
    
    def increment_usage(self):
        """增加使用计数"""
        from django.utils import timezone
        self.usage_count += 1
        self.last_used_at = timezone.now()
        self.save(update_fields=['usage_count', 'last_used_at'])

class AIModelTemplate(models.Model):
    """AI模型配置模板"""
    
    provider = models.CharField(
        max_length=20,
        choices=AIModelProvider.choices,
        unique=True
    )
    
    default_api_url = models.URLField(
        help_text="默认API端点URL"
    )
    
    supported_models = models.JSONField(
        default=list,
        help_text="支持的模型列表"
    )
    
    default_config = models.JSONField(
        default=dict,
        help_text="默认配置参数"
    )
    
    required_fields = models.JSONField(
        default=list,
        help_text="必需的配置字段"
    )
    
    documentation_url = models.URLField(
        blank=True,
        help_text="文档链接"
    )
    
    class Meta:
        db_table = 'ai_model_template'
        verbose_name = 'AI模型模板'
        verbose_name_plural = 'AI模型模板'
    
    def __str__(self):
        return f"{self.get_provider_display()} Template"

# 预定义模板数据
AI_MODEL_TEMPLATES = {
    AIModelProvider.OPENAI: {
        'default_api_url': 'https://api.openai.com/v1',
        'supported_models': [
            'gpt-4o',
            'gpt-4o-mini', 
            'gpt-4-turbo',
            'gpt-4',
            'gpt-3.5-turbo'
        ],
        'default_config': {
            'temperature': 0.7,
            'max_tokens': 4000,
            'top_p': 1.0,
            'frequency_penalty': 0.0,
            'presence_penalty': 0.0
        },
        'required_fields': ['api_key'],
        'documentation_url': 'https://platform.openai.com/docs/api-reference'
    },
    AIModelProvider.GOOGLE: {
        'default_api_url': 'https://generativelanguage.googleapis.com/v1',
        'supported_models': [
            'gemini-1.5-pro',
            'gemini-1.5-flash',
            'gemini-pro',
            'gemini-pro-vision'
        ],
        'default_config': {
            'temperature': 0.7,
            'max_output_tokens': 4000,
            'top_p': 0.95,
            'top_k': 40
        },
        'required_fields': ['api_key'],
        'documentation_url': 'https://ai.google.dev/docs'
    },
    AIModelProvider.ANTHROPIC: {
        'default_api_url': 'https://api.anthropic.com/v1',
        'supported_models': [
            'claude-3-5-sonnet-20241022',
            'claude-3-opus-20240229',
            'claude-3-sonnet-20240229',
            'claude-3-haiku-20240307'
        ],
        'default_config': {
            'temperature': 0.7,
            'max_tokens': 4000,
            'top_p': 1.0
        },
        'required_fields': ['api_key'],
        'documentation_url': 'https://docs.anthropic.com/claude/reference'
    },
    AIModelProvider.AZURE_OPENAI: {
        'default_api_url': 'https://your-resource.openai.azure.com/openai/deployments',
        'supported_models': [
            'gpt-4',
            'gpt-4-turbo',
            'gpt-35-turbo'
        ],
        'default_config': {
            'temperature': 0.7,
            'max_tokens': 4000,
            'api_version': '2024-02-15-preview'
        },
        'required_fields': ['api_key', 'deployment_name'],
        'documentation_url': 'https://learn.microsoft.com/en-us/azure/ai-services/openai/'
    },
    AIModelProvider.OLLAMA: {
        'default_api_url': 'http://localhost:11434/api',
        'supported_models': [
            'llama2',
            'llama2:13b',
            'llama2:70b',
            'codellama',
            'mistral',
            'mixtral'
        ],
        'default_config': {
            'temperature': 0.7,
            'num_predict': 4000
        },
        'required_fields': [],
        'documentation_url': 'https://ollama.ai/docs'
    }
} 