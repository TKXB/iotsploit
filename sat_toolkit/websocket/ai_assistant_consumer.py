import asyncio
import json
import threading
import queue
import sys
import io
from contextlib import redirect_stdout, redirect_stderr
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import subprocess
from threading import Thread
import signal
import os
from ..models.AIModel_Model import AIModelConfig
from ..mcp.tools import ToolHandler
from ..tools.xlogger import xlog
from sat_toolkit.core.device_manager import DeviceDriverManager

class AIAssistantConsumer(AsyncWebsocketConsumer):
    """AI助手WebSocket消费者，处理智能终端会话"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.assistant_process = None
        self.output_queue = queue.Queue()
        self.input_queue = queue.Queue()
        self.session_id = None
        self.shell_thread = None
        # MCP 工具处理器将在 connect 中延迟初始化，避免在异步上下文中执行同步数据库操作
        self.mcp_tool_handler = None
        xlog.info("AIAssistantConsumer initialized", "ai_assistant")
        
    async def connect(self):
        """建立WebSocket连接"""
        xlog.info("WebSocket connection attempt started", "ai_assistant")
        await self.accept()
        self.session_id = self.scope['url_route']['kwargs'].get('session_id', 'default')
        xlog.info(f"WebSocket connection accepted for session: {self.session_id}", "ai_assistant")

        # 延迟初始化 MCP 工具处理器，使用线程安全的同步到异步包装器
        if self.mcp_tool_handler is None:
            try:
                xlog.info("Initializing MCP ToolHandler...", "ai_assistant")
                self.mcp_tool_handler = await database_sync_to_async(ToolHandler)()
                xlog.info("MCP ToolHandler initialized successfully", "ai_assistant")
            except Exception as e:
                xlog.error(f"Failed to initialize ToolHandler: {str(e)}", "ai_assistant")
                await self.send_error(f"Failed to initialize ToolHandler: {str(e)}")
                return
        
        # 启动AI助手会话
        await self.start_assistant_session()
        
    async def disconnect(self, close_code):
        """断开连接时清理资源"""
        xlog.info(f"WebSocket disconnecting with code: {close_code}, session: {self.session_id}", "ai_assistant")
        await self.cleanup_session()
        
    async def receive(self, text_data):
        """接收来自前端的消息"""
        try:
            xlog.debug(f"Received WebSocket message: {text_data[:200]}...", "ai_assistant")
            data = json.loads(text_data)
            message_type = data.get('type')
            xlog.info(f"Processing message type: {message_type}", "ai_assistant")
            
            if message_type == 'command':
                await self.handle_command(data.get('command', ''))
            elif message_type == 'interrupt':
                await self.handle_interrupt()
            elif message_type == 'resize':
                await self.handle_resize(data.get('rows', 24), data.get('cols', 80))
            elif message_type == 'ai_query':
                query = data.get('query', '')
                xlog.info(f"Handling AI query: '{query}'", "ai_assistant")
                await self.handle_ai_query(query)
            else:
                xlog.warning(f"Unknown message type: {message_type}", "ai_assistant")
                
        except json.JSONDecodeError as e:
            xlog.error(f"Invalid JSON received: {str(e)}", "ai_assistant")
            await self.send_error("Invalid JSON received")
        except Exception as e:
            xlog.error(f"Error processing WebSocket message: {str(e)}", "ai_assistant")
            await self.send_error(f"Error processing message: {str(e)}")
            
    async def handle_command(self, command):
        """处理命令输入"""
        xlog.info(f"Handling command: {command}", "ai_assistant")
        if self.shell_thread and self.shell_thread.is_alive():
            # 将命令发送到shell线程
            self.input_queue.put(command + '\n')
            xlog.debug("Command sent to shell thread", "ai_assistant")
        else:
            xlog.error("AI Assistant session not active", "ai_assistant")
            await self.send_error("AI Assistant session not active")
            
    async def handle_ai_query(self, query):
        """处理AI查询请求"""
        xlog.info(f"Processing AI query: '{query}'", "ai_assistant")
        await self.send_ai_response(f"AI: Processing query '{query}'...")
        
        # 获取默认AI模型配置
        try:
            xlog.debug("Getting default AI config...", "ai_assistant")
            ai_config = await self.get_default_ai_config()
            xlog.info(f"AI config retrieved: {ai_config.model_name if ai_config else 'None'}", "ai_assistant")
        except Exception as e:
            xlog.error(f"Error getting AI config: {str(e)}", "ai_assistant")
            ai_config = None
        
        if ai_config:
            try:
                # 使用AI模型处理查询
                xlog.info(f"Processing with AI model: {ai_config.provider}/{ai_config.model_name}", "ai_assistant")
                response = await self.process_with_ai_model(query, ai_config)
                xlog.info(f"AI model response received: {response[:100]}...", "ai_assistant")
                await self.send_ai_response(f"AI: {response}")
            except Exception as e:
                xlog.error(f"Error processing with AI model: {str(e)}", "ai_assistant")
                await self.send_ai_response(f"AI: Error processing with AI model: {str(e)}")
        else:
            xlog.info("No AI config found, using fallback command mapping", "ai_assistant")
            # 回退到简单的命令映射
            command_mapping = {
                "list devices": "list_devices",
                "show devices": "list_devices", 
                "scan for devices": "scan_devices",
                "list plugins": "list_plugins",
                "show exploits": "list_plugins",
                "help": "help",
                "start server": "runserver",
                "hello": "help",
                "hi": "help"
            }
            
            suggested_command = command_mapping.get(query.lower())
            if suggested_command:
                xlog.info(f"Suggested command for '{query}': {suggested_command}", "ai_assistant")
                await self.send_ai_response(f"AI: Suggested command: {suggested_command}")
            else:
                xlog.info(f"No command mapping found for: '{query}'", "ai_assistant")
                await self.send_ai_response("AI: I'm not sure how to help with that. Try 'help' for available commands.")
    
    @database_sync_to_async
    def get_default_ai_config(self):
        """获取默认AI模型配置"""
        try:
            xlog.debug("Querying database for default AI config", "ai_assistant")
            config = AIModelConfig.objects.filter(is_default=True, is_active=True).first()
            if config:
                xlog.info(f"Found default AI config: {config.provider}/{config.model_name}", "ai_assistant")
            else:
                xlog.warning("No default AI config found in database", "ai_assistant")
            return config
        except Exception as e:
            xlog.error(f"Database error getting AI config: {str(e)}", "ai_assistant")
            return None
    
    @database_sync_to_async
    def update_ai_usage(self, ai_config):
        """更新AI模型使用统计"""
        try:
            ai_config.increment_usage()
            xlog.debug(f"Updated usage stats for AI config: {ai_config.model_name}", "ai_assistant")
        except Exception as e:
            xlog.error(f"Error updating AI usage: {str(e)}", "ai_assistant")
            pass
    
    async def get_mcp_tools(self):
        """获取MCP工具定义"""
        # 定义SAT工具的MCP工具规范
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "list_plugins",
                    "description": "List all available exploit plugins in the SAT framework",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function", 
                "function": {
                    "name": "list_devices",
                    "description": "List all connected devices",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "scan_devices", 
                    "description": "Scan for new devices",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_targets",
                    "description": "List all available targets",
                    "parameters": {
                        "type": "object", 
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_plugin",
                    "description": "Execute a specific exploit plugin",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "plugin_name": {
                                "type": "string",
                                "description": "Name of the plugin to execute"
                            }
                        },
                        "required": ["plugin_name"]
                    }
                }
            }
        ]
        return tools
    
    async def handle_tool_calls(self, message, ai_config):
        """处理OpenAI工具调用"""
        results = []
        
        for tool_call in message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            # 执行SAT命令
            result = await self.execute_sat_command(function_name, function_args)
            results.append(f"Executed {function_name}: {result}")
        
        # 更新使用统计
        await self.update_ai_usage(ai_config)
        
        return "\n".join(results)
    
    async def handle_claude_tool_calls(self, response, ai_config):
        """处理Claude工具调用"""
        results = []
        
        for block in response.content:
            if block.type == "tool_use":
                function_name = block.name
                function_args = block.input
                
                # 执行SAT命令
                result = await self.execute_sat_command(function_name, function_args)
                results.append(f"Executed {function_name}: {result}")
        
        # 更新使用统计
        await self.update_ai_usage(ai_config)
        
        return "\n".join(results)
    
    async def execute_sat_command(self, command_name, args):
        """执行SAT命令 - 通过MCP工具处理器"""
        try:
            # 映射命令名称到MCP工具名称
            tool_mapping = {
                "list_plugins": "get_system_status",  # 系统状态包含插件信息
                "list_devices": "scan_devices", 
                "scan_devices": "scan_devices",
                "list_targets": "get_system_status",  # 系统状态包含目标信息
                "execute_plugin": "execute_safe_exploit"
            }
            
            mcp_tool_name = tool_mapping.get(command_name)
            if not mcp_tool_name:
                return f"Unknown command: {command_name}"
            
            # 准备MCP工具参数
            mcp_args = {}
            if command_name == "execute_plugin":
                mcp_args = {
                    "exploit_name": args.get("plugin_name", ""),
                    "parameters": {}
                }
            elif command_name in ["list_devices", "scan_devices"]:
                # 扫描所有可用的启用驱动，而不是只扫描第一个
                device_manager = DeviceDriverManager()
                enabled_drivers = [
                    driver for driver in device_manager.list_drivers() 
                    if device_manager.is_driver_enabled(driver)
                ]
                
                if enabled_drivers:
                    # 扫描所有启用的驱动
                    all_results = []
                    for driver_name in enabled_drivers:
                        try:
                            result = await database_sync_to_async(self.mcp_tool_handler.execute_tool)("scan_devices", {"driver_name": driver_name})
                            if result and len(result) > 0:
                                all_results.append(f"Driver '{driver_name}': {result[0].text}")
                        except Exception as e:
                            all_results.append(f"Driver '{driver_name}': Error - {str(e)}")
                    
                    return "\n".join(all_results) if all_results else "No devices found across all drivers"
                else:
                    # 如果没有启用的驱动，返回错误信息
                    return "No enabled device drivers available. Please enable at least one driver."
            
            # 通过MCP工具处理器执行（在线程中调用以避免在异步上下文中进行同步数据库操作）
            result = await database_sync_to_async(self.mcp_tool_handler.execute_tool)(mcp_tool_name, mcp_args)
            
            # 提取文本结果
            if result and len(result) > 0:
                return result[0].text
            else:
                return "No result returned from MCP tool"
                
        except Exception as e:
            # 如果MCP工具失败，回退到直接API调用
            return await self.fallback_to_api(command_name, args, str(e))
    
    async def fallback_to_api(self, command_name, args, mcp_error):
        """MCP工具失败时的API回退机制"""
        try:
            if command_name == "list_plugins":
                return await self.call_sat_api("/api/list_plugins/")
            elif command_name == "list_devices":
                return await self.call_sat_api("/api/list_devices/")
            elif command_name == "scan_devices":
                return await self.call_sat_api("/api/scan_devices/")
            elif command_name == "list_targets":
                return await self.call_sat_api("/api/list_targets/")
            elif command_name == "execute_plugin":
                plugin_name = args.get("plugin_name")
                if plugin_name:
                    return await self.call_sat_api("/api/execute_plugin/", {"plugin_name": plugin_name})
                else:
                    return "Error: plugin_name is required"
            else:
                return f"Unknown command: {command_name} (MCP error: {mcp_error})"
        except Exception as e:
            return f"Both MCP and API failed - MCP: {mcp_error}, API: {str(e)}"
    
    async def call_sat_api(self, endpoint, data=None):
        """调用SAT API"""
        try:
            import aiohttp
            
            url = f"http://localhost:8888{endpoint}"
            
            async with aiohttp.ClientSession() as session:
                if data:
                    async with session.post(url, json=data) as response:
                        result = await response.json()
                else:
                    async with session.get(url) as response:
                        result = await response.json()
                
                return json.dumps(result, indent=2)
        except Exception as e:
            return f"API call failed: {str(e)}"
    
    async def process_with_ai_model(self, query, ai_config):
        """使用AI模型处理查询"""
        try:
            xlog.info(f"Starting AI model processing for provider: {ai_config.provider}", "ai_assistant")
            # 这里可以实现实际的AI模型调用
            # 根据不同的provider调用不同的API
            
            if ai_config.provider == 'openai':
                xlog.debug("Calling OpenAI API", "ai_assistant")
                return await self.call_openai_api(query, ai_config)
            elif ai_config.provider == 'google':
                xlog.debug("Calling Google API", "ai_assistant")
                return await self.call_google_api(query, ai_config)
            elif ai_config.provider == 'anthropic':
                xlog.debug("Calling Anthropic API", "ai_assistant")
                return await self.call_anthropic_api(query, ai_config)
            else:
                xlog.warning(f"Unsupported AI provider: {ai_config.provider}", "ai_assistant")
                return "AI model not supported yet"
                
        except Exception as e:
            xlog.error(f"Error in process_with_ai_model: {str(e)}", "ai_assistant")
            return f"Error processing with AI model: {str(e)}"
    
    async def call_openai_api(self, query, ai_config):
        """调用OpenAI API"""
        try:
            xlog.info("Attempting to import OpenAI library", "ai_assistant")
            from openai import AsyncOpenAI
            import asyncio
            
            # 初始化OpenAI客户端
            xlog.debug(f"Initializing OpenAI client with base_url: {ai_config.api_url}", "ai_assistant")
            client = AsyncOpenAI(
                api_key=ai_config.get_api_key(),
                base_url=ai_config.api_url
            )
            
            # 构建系统提示，让AI了解SAT工具的功能和MCP工具
            system_prompt = """You are an AI assistant for the SAT (Security Assessment Toolkit) penetration testing framework.

Available SAT commands include:
- list_devices: List all connected devices
- scan_devices: Scan for new devices  
- list_plugins: List available exploit plugins
- list_targets: List available targets
- execute_plugin <plugin_name>: Execute a specific plugin
- help: Show help information

You have access to MCP (Model Context Protocol) tools that can directly execute SAT commands.
When users ask about exploits, devices, or security testing, you can:
1. Provide helpful explanations
2. Suggest relevant SAT commands
3. Use MCP tools to execute commands directly when appropriate

For example, when asked about "available exploits", you should use the list_plugins MCP tool."""

            # 构建消息
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ]
            
            xlog.debug("Getting MCP tools for OpenAI", "ai_assistant")
            # 检查是否有MCP工具可用
            tools = await self.get_mcp_tools()
            xlog.info(f"Found {len(tools)} MCP tools available", "ai_assistant")
            
            # 调用OpenAI API
            if tools:
                xlog.debug("Making OpenAI API call with tools", "ai_assistant")
                # 使用工具调用
                response = await client.chat.completions.create(
                    model=ai_config.model_name,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    max_tokens=ai_config.extra_config.get('max_tokens', 1000),
                    temperature=ai_config.extra_config.get('temperature', 0.7)
                )
                
                xlog.info("OpenAI API response received", "ai_assistant")
                # 处理工具调用
                if response.choices[0].message.tool_calls:
                    xlog.info(f"Processing {len(response.choices[0].message.tool_calls)} tool calls", "ai_assistant")
                    tool_result = await self.handle_tool_calls(response.choices[0].message, ai_config)
                    xlog.info(f"OpenAI API tool call result: {tool_result[:200]}...", "ai_assistant")
                    return tool_result
                else:
                    xlog.debug("No tool calls in response, returning content", "ai_assistant")
                    ai_response = response.choices[0].message.content
                    xlog.info(f"OpenAI API response: {ai_response[:200]}...", "ai_assistant")
                    return ai_response
            else:
                xlog.debug("Making OpenAI API call without tools", "ai_assistant")
                # 普通对话
                response = await client.chat.completions.create(
                    model=ai_config.model_name,
                    messages=messages,
                    max_tokens=ai_config.extra_config.get('max_tokens', 1000),
                    temperature=ai_config.extra_config.get('temperature', 0.7)
                )
                
                xlog.info("OpenAI API response received (no tools)", "ai_assistant")
                ai_response = response.choices[0].message.content
                xlog.info(f"OpenAI API response (no tools): {ai_response[:200]}...", "ai_assistant")
                return ai_response
                
        except ImportError:
            xlog.error("OpenAI library not available", "ai_assistant")
            return "OpenAI library not available. Please install it: pip install openai"
        except Exception as e:
            xlog.error(f"Error calling OpenAI API: {str(e)}", "ai_assistant")
            return f"Error calling OpenAI API: {str(e)}"
    
    async def call_google_api(self, query, ai_config):
        """调用Google Gemini API"""
        try:
            import google.generativeai as genai
            import asyncio
            
            # 配置Google AI
            genai.configure(api_key=ai_config.get_api_key())
            
            # 构建系统提示
            system_prompt = """You are an AI assistant for the SAT (Security Assessment Toolkit) penetration testing framework.

Available SAT commands include:
- list_devices: List all connected devices
- scan_devices: Scan for new devices  
- list_plugins: List available exploit plugins
- list_targets: List available targets
- execute_plugin <plugin_name>: Execute a specific plugin
- help: Show help information

When users ask about exploits, devices, or security testing, provide helpful explanations and suggest relevant SAT commands."""

            # 初始化模型
            model = genai.GenerativeModel(
                model_name=ai_config.model_name,
                system_instruction=system_prompt
            )
            
            # 配置生成参数
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=ai_config.extra_config.get('max_tokens', 1000),
                temperature=ai_config.extra_config.get('temperature', 0.7)
            )
            
            # 生成响应
            response = await asyncio.to_thread(
                model.generate_content,
                query,
                generation_config=generation_config
            )
            
            ai_response = response.text if response.text else "No response from Gemini"
            xlog.info(f"Google Gemini API response: {ai_response[:200]}...", "ai_assistant")
            return ai_response
                
        except ImportError:
            return "Google Generative AI library not available. Please install it: pip install google-generativeai"
        except Exception as e:
            return f"Error calling Google Gemini API: {str(e)}"
    
    async def call_anthropic_api(self, query, ai_config):
        """调用Anthropic Claude API"""
        try:
            from anthropic import AsyncAnthropic
            
            # 初始化Anthropic客户端
            client = AsyncAnthropic(
                api_key=ai_config.get_api_key(),
                base_url=ai_config.api_url if ai_config.api_url != "https://api.anthropic.com/v1" else None
            )
            
            # 构建系统提示
            system_prompt = """You are an AI assistant for the SAT (Security Assessment Toolkit) penetration testing framework.

Available SAT commands include:
- list_devices: List all connected devices
- scan_devices: Scan for new devices  
- list_plugins: List available exploit plugins
- list_targets: List available targets
- execute_plugin <plugin_name>: Execute a specific plugin
- help: Show help information

You have access to MCP (Model Context Protocol) tools that can directly execute SAT commands.
When users ask about exploits, devices, or security testing, provide helpful explanations and suggest relevant commands."""

            # 检查是否有MCP工具可用
            tools = await self.get_mcp_tools()
            
            # 调用Claude API
            if tools:
                # 使用工具调用
                response = await client.messages.create(
                    model=ai_config.model_name,
                    max_tokens=ai_config.extra_config.get('max_tokens', 1000),
                    temperature=ai_config.extra_config.get('temperature', 0.7),
                    system=system_prompt,
                    messages=[{"role": "user", "content": query}],
                    tools=tools
                )
                
                # 处理工具调用
                if response.content and any(block.type == "tool_use" for block in response.content):
                    tool_result = await self.handle_claude_tool_calls(response, ai_config)
                    xlog.info(f"Claude API tool call result: {tool_result[:200]}...", "ai_assistant")
                    return tool_result
                else:
                    ai_response = response.content[0].text if response.content else "No response"
                    xlog.info(f"Claude API response: {ai_response[:200]}...", "ai_assistant")
                    return ai_response
            else:
                # 普通对话
                response = await client.messages.create(
                    model=ai_config.model_name,
                    max_tokens=ai_config.extra_config.get('max_tokens', 1000),
                    temperature=ai_config.extra_config.get('temperature', 0.7),
                    system=system_prompt,
                    messages=[{"role": "user", "content": query}]
                )
                
                ai_response = response.content[0].text if response.content else "No response"
                xlog.info(f"Claude API response (no tools): {ai_response[:200]}...", "ai_assistant")
                return ai_response
                
        except ImportError:
            return "Anthropic library not available. Please install it: pip install anthropic"
        except Exception as e:
            return f"Error calling Anthropic API: {str(e)}"
            
    async def handle_interrupt(self):
        """处理中断信号 (Ctrl+C)"""
        if self.assistant_process:
            try:
                self.assistant_process.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass
                
    async def handle_resize(self, rows, cols):
        """处理终端大小调整"""
        # 可以实现终端大小调整逻辑
        pass
        
    async def start_assistant_session(self):
        """启动AI助手会话"""
        try:
            xlog.info("Starting AI assistant session", "ai_assistant")
            # 启动shell线程
            self.shell_thread = Thread(target=self.run_shell_session, daemon=True)
            self.shell_thread.start()
            xlog.debug("Shell thread started", "ai_assistant")
            
            # 启动输出监听线程
            output_thread = Thread(target=self.monitor_output, daemon=True)
            output_thread.start()
            xlog.debug("Output monitor thread started", "ai_assistant")
            
        except Exception as e:
            xlog.error(f"Failed to start AI assistant: {str(e)}", "ai_assistant")
            await self.send_error(f"Failed to start AI assistant: {str(e)}")
            
    def run_shell_session(self):
        """在独立线程中运行SAT Shell"""
        try:
            xlog.info("Starting shell session in thread", "ai_assistant")
            # 设置环境变量
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['AI_ASSISTANT_MODE'] = '1'  # 标识AI助手模式
            
            # 启动Python控制台，使用console.py
            cmd = [sys.executable, 'console.py']
            xlog.debug(f"Starting process with command: {' '.join(cmd)}", "ai_assistant")
            
            self.assistant_process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 合并错误输出
                text=True,
                bufsize=0,  # 无缓冲
                env=env,
                cwd=os.path.dirname(os.path.abspath(__file__)) + '/../../'
            )
            
            xlog.info(f"Shell process started with PID: {self.assistant_process.pid}", "ai_assistant")
            
            # 监听输入队列
            def input_handler():
                xlog.debug("Input handler thread started", "ai_assistant")
                while self.assistant_process and self.assistant_process.poll() is None:
                    try:
                        command = self.input_queue.get(timeout=0.1)
                        if self.assistant_process and self.assistant_process.stdin:
                            xlog.debug(f"Sending command to process: {command.strip()}", "ai_assistant")
                            self.assistant_process.stdin.write(command)
                            self.assistant_process.stdin.flush()
                    except queue.Empty:
                        continue
                    except (BrokenPipeError, OSError) as e:
                        xlog.error(f"Input handler pipe error: {str(e)}", "ai_assistant")
                        break
                xlog.debug("Input handler thread ended", "ai_assistant")
                        
            input_thread = Thread(target=input_handler, daemon=True)
            input_thread.start()
            
            # 监听输出
            if self.assistant_process.stdout:
                xlog.debug("Starting output monitoring", "ai_assistant")
                for line in iter(self.assistant_process.stdout.readline, ''):
                    if line:
                        xlog.debug(f"Process output: {line.strip()}", "ai_assistant")
                        self.output_queue.put(('stdout', line))
                    if self.assistant_process.poll() is not None:
                        break
                        
            xlog.info("Shell session ended", "ai_assistant")
                        
        except Exception as e:
            xlog.error(f"Shell error: {str(e)}", "ai_assistant")
            self.output_queue.put(('error', f"Shell error: {str(e)}"))
            
    def monitor_output(self):
        """监听输出队列并发送到WebSocket"""
        from channels.db import database_sync_to_async
        from asgiref.sync import async_to_sync
        
        xlog.debug("Output monitor started", "ai_assistant")
        while True:
            try:
                output_type, data = self.output_queue.get(timeout=0.1)
                
                # 使用 async_to_sync 来安全地调用异步方法
                try:
                    async_to_sync(self.send_output)(output_type, data)
                except Exception as e:
                    xlog.error(f"Failed to send output: {e}", "ai_assistant")
                    continue
                
            except queue.Empty:
                continue
            except Exception as e:
                xlog.error(f"Output monitor error: {e}", "ai_assistant")
                break
                
    async def send_output(self, output_type, data):
        """发送输出到前端"""
        try:
            xlog.debug(f"Sending output type: {output_type}, data length: {len(str(data))}", "ai_assistant")
            await self.send(text_data=json.dumps({
                'type': 'output',
                'output_type': output_type,
                'data': data
            }))
        except Exception as e:
            xlog.error(f"Error sending output: {str(e)}", "ai_assistant")
        
    async def send_ai_response(self, message):
        """发送AI响应消息"""
        try:
            xlog.info(f"Sending AI response: {message[:100]}...", "ai_assistant")
            await self.send(text_data=json.dumps({
                'type': 'ai_response',
                'message': message
            }))
            xlog.debug("AI response sent successfully", "ai_assistant")
        except Exception as e:
            xlog.error(f"Error sending AI response: {str(e)}", "ai_assistant")
        
    async def send_error(self, error_message):
        """发送错误消息"""
        try:
            xlog.error(f"Sending error message: {error_message}", "ai_assistant")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': error_message
            }))
        except Exception as e:
            xlog.error(f"Error sending error message: {str(e)}", "ai_assistant")
        
    async def cleanup_session(self):
        """清理会话资源"""
        xlog.info("Cleaning up AI assistant session", "ai_assistant")
        if self.assistant_process:
            try:
                xlog.debug(f"Terminating process PID: {self.assistant_process.pid}", "ai_assistant")
                self.assistant_process.terminate()
                self.assistant_process.wait(timeout=5)
                xlog.info("Process terminated successfully", "ai_assistant")
            except subprocess.TimeoutExpired:
                xlog.warning("Process termination timeout, killing process", "ai_assistant")
                self.assistant_process.kill()
            except Exception as e:
                xlog.error(f"Error during process cleanup: {str(e)}", "ai_assistant")
                pass
            finally:
                self.assistant_process = None 
                xlog.debug("Process cleanup completed", "ai_assistant") 