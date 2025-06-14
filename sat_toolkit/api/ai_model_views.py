from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db import transaction
import json

from ..models.AIModel_Model import AIModelConfig, AIModelTemplate, AI_MODEL_TEMPLATES, AIModelProvider
from ..serializers.ai_model_serializers import (
    AIModelConfigSerializer, 
    AIModelConfigCreateSerializer,
    AIModelTemplateSerializer
)

class AIModelConfigViewSet(viewsets.ModelViewSet):
    """AI模型配置管理API"""
    
    queryset = AIModelConfig.objects.all()
    serializer_class = AIModelConfigSerializer
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return AIModelConfigCreateSerializer
        return AIModelConfigSerializer
    
    @action(detail=False, methods=['get'])
    def templates(self, request):
        """获取所有AI模型模板"""
        templates = []
        for provider, template_data in AI_MODEL_TEMPLATES.items():
            templates.append({
                'provider': provider,
                'provider_display': dict(AIModelProvider.choices)[provider],
                **template_data
            })
        
        return Response({
            'success': True,
            'data': templates
        })
    
    @action(detail=False, methods=['get'])
    def providers(self, request):
        """获取所有支持的AI提供商"""
        providers = []
        for provider, display_name in AIModelProvider.choices:
            template = AI_MODEL_TEMPLATES.get(provider, {})
            providers.append({
                'value': provider,
                'label': display_name,
                'default_url': template.get('default_api_url', ''),
                'supported_models': template.get('supported_models', []),
                'required_fields': template.get('required_fields', []),
                'documentation_url': template.get('documentation_url', '')
            })
        
        return Response({
            'success': True,
            'data': providers
        })
    
    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """测试AI模型连接"""
        config = self.get_object()
        
        try:
            result = config.test_connection()
            return Response({
                'success': result['success'],
                'message': result['message'],
                'response_time': result['response_time']
            })
        except Exception as e:
            return Response({
                'success': False,
                'message': f'连接测试失败: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """设置为默认配置"""
        config = self.get_object()
        
        with transaction.atomic():
            # 清除其他默认配置
            AIModelConfig.objects.filter(is_default=True).update(is_default=False)
            # 设置当前配置为默认
            config.is_default = True
            config.save()
        
        return Response({
            'success': True,
            'message': f'已将 {config.name} 设置为默认配置'
        })
    
    @action(detail=False, methods=['get'])
    def default(self, request):
        """获取默认配置"""
        try:
            default_config = AIModelConfig.objects.filter(is_default=True, is_active=True).first()
            if default_config:
                serializer = self.get_serializer(default_config)
                return Response({
                    'success': True,
                    'data': serializer.data
                })
            else:
                return Response({
                    'success': False,
                    'message': '未找到默认配置'
                }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def create_from_template(self, request):
        """从模板创建配置"""
        provider = request.data.get('provider')
        name = request.data.get('name')
        api_key = request.data.get('api_key')
        model_name = request.data.get('model_name')
        custom_config = request.data.get('custom_config', {})
        
        if not all([provider, name, api_key, model_name]):
            return Response({
                'success': False,
                'message': '缺少必需参数: provider, name, api_key, model_name'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        template = AI_MODEL_TEMPLATES.get(provider)
        if not template:
            return Response({
                'success': False,
                'message': f'不支持的提供商: {provider}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # 合并默认配置和自定义配置
            extra_config = {**template['default_config'], **custom_config}
            
            config = AIModelConfig(
                name=name,
                provider=provider,
                model_name=model_name,
                api_url=template['default_api_url'],
                extra_config=extra_config
            )
            config.set_api_key(api_key)
            config.save()
            
            serializer = self.get_serializer(config)
            return Response({
                'success': True,
                'message': f'成功创建配置: {name}',
                'data': serializer.data
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({
                'success': False,
                'message': f'创建配置失败: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def update_api_key(self, request, pk=None):
        """更新API密钥"""
        config = self.get_object()
        api_key = request.data.get('api_key')
        
        if not api_key:
            return Response({
                'success': False,
                'message': 'API密钥不能为空'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            config.set_api_key(api_key)
            config.save()
            
            return Response({
                'success': True,
                'message': 'API密钥更新成功'
            })
        except Exception as e:
            return Response({
                'success': False,
                'message': f'更新API密钥失败: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def usage_stats(self, request):
        """获取使用统计"""
        configs = AIModelConfig.objects.all()
        stats = []
        
        for config in configs:
            stats.append({
                'id': config.id,
                'name': config.name,
                'provider': config.get_provider_display(),
                'usage_count': config.usage_count,
                'last_used_at': config.last_used_at,
                'is_active': config.is_active,
                'is_default': config.is_default
            })
        
        return Response({
            'success': True,
            'data': stats
        })

class AIModelTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    """AI模型模板API（只读）"""
    
    queryset = AIModelTemplate.objects.all()
    serializer_class = AIModelTemplateSerializer
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'])
    def initialize_templates(self, request):
        """初始化预定义模板"""
        created_count = 0
        
        for provider, template_data in AI_MODEL_TEMPLATES.items():
            template, created = AIModelTemplate.objects.get_or_create(
                provider=provider,
                defaults=template_data
            )
            if created:
                created_count += 1
        
        return Response({
            'success': True,
            'message': f'成功初始化 {created_count} 个模板',
            'total_templates': len(AI_MODEL_TEMPLATES)
        }) 