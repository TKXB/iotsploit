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
import aiohttp
from ..models.AIModel_Model import AIModelConfig
from ..tools.xlogger import xlog

class AIAssistantConsumer(AsyncWebsocketConsumer):
    """AI助手WebSocket消费者，处理智能终端会话"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.assistant_process = None
        self.output_queue = queue.Queue()
        self.input_queue = queue.Queue()
        self.session_id = None
        self.shell_thread = None
        self.mcp_websocket_url = "ws://localhost:9998"
        xlog.info("AIAssistantConsumer initialized", "ai_assistant")
        
    async def connect(self):
        """建立WebSocket连接"""
        xlog.info("WebSocket connection attempt started", "ai_assistant")
        await self.accept()
        self.session_id = self.scope['url_route']['kwargs'].get('session_id', 'default')
        xlog.info(f"WebSocket connection accepted for session: {self.session_id}", "ai_assistant")
        
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
            command_mapping = {
                "list devices": "scan_devices",
                "show devices": "scan_devices", 
                "scan for devices": "scan_devices",
                "list plugins": "get_system_status",
                "show exploits": "get_system_status",
                "help": "get_system_status",
                "status": "get_system_status",
                "hello": "get_system_status",
                "hi": "get_system_status",
                "list serial ports": "list_serial_ports",
                "show serial ports": "list_serial_ports",
                "serial ports": "list_serial_ports",
                "list serial": "list_serial_ports",
                "read serial": "read_serial_port",
                "serial read": "read_serial_port",
                "analyze serial": "read_serial_port",
                "picocom": "read_serial_port",
                "connect serial": "read_serial_port"
            }
            
            suggested_command = command_mapping.get(query.lower())
            if suggested_command:
                xlog.info(f"Suggested command for '{query}': {suggested_command}", "ai_assistant")
                # Execute the MCP tool directly
                try:
                    result = await self.execute_mcp_tool(suggested_command, {})
                    await self.send_ai_response(f"AI: {result}")
                except Exception as e:
                    await self.send_ai_response(f"AI: Error executing command: {str(e)}")
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
    
    async def execute_mcp_tool(self, tool_name, arguments):
        """通过WebSocket连接到MCP桥接器执行工具"""
        try:
            xlog.info(f"=== MCP TOOL CALL START ===", "ai_assistant")
            xlog.info(f"Tool Name: {tool_name}", "ai_assistant")
            xlog.info(f"Arguments Type: {type(arguments)}", "ai_assistant")
            xlog.info(f"Arguments Content: {arguments}", "ai_assistant")
            xlog.info(f"Arguments JSON: {json.dumps(arguments)}", "ai_assistant")
            
            async with aiohttp.ClientSession() as session:
                xlog.info(f"Connecting to MCP WebSocket: {self.mcp_websocket_url}", "ai_assistant")
                async with session.ws_connect(self.mcp_websocket_url) as ws:
                    request = {
                        "type": "mcp_call_tool",
                        "tool_name": tool_name,
                        "arguments": arguments
                    }
                    
                    xlog.info(f"Sending MCP request: {json.dumps(request, indent=2)}", "ai_assistant")
                    await ws.send_str(json.dumps(request))
                    xlog.info(f"MCP request sent successfully", "ai_assistant")
                    
                    xlog.info(f"Waiting for MCP response...", "ai_assistant")
                    response = await ws.receive()
                    xlog.info(f"MCP response received - Type: {response.type}", "ai_assistant")
                    
                    if response.type == aiohttp.WSMsgType.TEXT:
                        xlog.info(f"MCP response data: {response.data}", "ai_assistant")
                        data = json.loads(response.data)
                        xlog.info(f"MCP response parsed: {json.dumps(data, indent=2)}", "ai_assistant")
                        
                        if data.get("type") == "tool_result":
                            result = data.get("result", "")
                            xlog.info(f"Tool result type: {type(result)}", "ai_assistant")
                            xlog.info(f"Tool result content: {result}", "ai_assistant")
                            
                            extracted = self._extract_mcp_text(result)
                            xlog.info(f"Extracted result: {extracted}", "ai_assistant")
                            xlog.info(f"=== MCP TOOL CALL SUCCESS ===", "ai_assistant")
                            return extracted
                        elif data.get("type") == "tool_error":
                            error_msg = data.get('error', 'Unknown error')
                            xlog.error(f"MCP tool error: {error_msg}", "ai_assistant")
                            xlog.info(f"=== MCP TOOL CALL ERROR ===", "ai_assistant")
                            return f"Tool error: {error_msg}"
                        else:
                            xlog.warning(f"Unexpected MCP response type: {data.get('type')}", "ai_assistant")
                            xlog.info(f"=== MCP TOOL CALL UNEXPECTED ===", "ai_assistant")
                            return f"Unexpected response: {data}"
                    else:
                        xlog.error(f"Invalid MCP response type: {response.type}", "ai_assistant")
                        xlog.info(f"=== MCP TOOL CALL FAILED ===", "ai_assistant")
                        return "Failed to get response from MCP bridge"
                        
        except Exception as e:
            xlog.error(f"Error executing MCP tool: {str(e)}", "ai_assistant")
            xlog.error(f"Exception type: {type(e)}", "ai_assistant")
            xlog.error(f"Exception details: {repr(e)}", "ai_assistant")
            xlog.info(f"=== MCP TOOL CALL EXCEPTION ===", "ai_assistant")
            return f"Error executing MCP tool: {str(e)}"
    
    def _extract_mcp_text(self, result) -> str:
        """Extract human-readable text from an MCP tool result.
        
        MCP standard format: {"content": [{"type": "text", "text": "..."}], "isError": false}
        Legacy list format:  [{"type": "text", "text": "..."}]
        """
        content_list = None
        if isinstance(result, dict):
            content_list = result.get("content")
        elif isinstance(result, list):
            content_list = result

        if isinstance(content_list, list) and content_list:
            texts = [
                item.get("text", "")
                for item in content_list
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            if texts:
                return "\n".join(texts)

        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False, indent=2)

    async def get_mcp_tools(self):
        """获取MCP工具定义"""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "scan_devices",
                    "description": "Scan for available devices",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "driver_name": {
                                "type": "string",
                                "description": "Device driver name or 'all' for all drivers"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_system_status",
                    "description": "Get overall system status",
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
                    "name": "list_serial_ports",
                    "description": "List available serial ports on the system",
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
                    "name": "read_serial_port",
                    "description": "Read and analyze serial port output with AI-powered pattern detection. Can detect login shells, device types, and firmware information.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "port": {
                                "type": "string",
                                "description": "Serial port path (e.g., /dev/ttyUSB0, COM1)",
                                "default": "/dev/ttyUSB0"
                            },
                            "baudrate": {
                                "type": "integer",
                                "description": "Baud rate for serial communication",
                                "default": 115200
                            },
                            "timeout": {
                                "type": "integer",
                                "description": "Maximum time to wait for output (seconds)",
                                "default": 30
                            },
                            "auto_interact": {
                                "type": "boolean",
                                "description": "Automatically send Enter and common inputs to trigger responses",
                                "default": True
                            }
                        },
                        "required": ["port"]
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
            
            result = await self.execute_mcp_tool(function_name, function_args)
            results.append(f"Executed {function_name}: {result}")
        
        await self.update_ai_usage(ai_config)
        
        return "\n".join(results)
    
    async def handle_claude_tool_calls(self, response, ai_config):
        """处理Claude工具调用"""
        results = []
        
        for block in response.content:
            if block.type == "tool_use":
                function_name = block.name
                function_args = block.input
                
                result = await self.execute_mcp_tool(function_name, function_args)
                results.append(f"Executed {function_name}: {result}")
        
        await self.update_ai_usage(ai_config)
        
        return "\n".join(results)
    
    async def process_with_ai_model(self, query, ai_config):
        """使用AI模型处理查询"""
        try:
            xlog.info(f"Starting AI model processing for provider: {ai_config.provider}", "ai_assistant")
            
            if ai_config.provider in ('openai', 'azure_openai', 'ollama'):
                xlog.debug(f"Calling OpenAI-compatible API ({ai_config.provider})", "ai_assistant")
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
            
            # Ollama stores /api as the base URL (for model listing), but its
            # OpenAI-compatible chat endpoint lives at /v1.
            base_url = ai_config.api_url
            if ai_config.provider == 'ollama' and base_url.rstrip('/').endswith('/api'):
                base_url = base_url.rstrip('/').rsplit('/api', 1)[0] + '/v1'
            xlog.debug(f"Initializing OpenAI client with base_url: {base_url}", "ai_assistant")
            api_key = ai_config.get_api_key() or 'ollama'  # Ollama doesn't need a real key
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url
            )
            
            system_prompt = """You are an AI assistant for the SAT (Security Assessment Toolkit) penetration testing framework.
You are a security testing assistant. You MUST use the tools available to you when the user requests an action.

## Remote tools (MCP, executed on the server)
- scan_devices: Discover connected hardware devices (USB, serial, etc.)
- get_system_status: Get overall system status
- list_serial_ports: List available serial ports
- read_serial_port: Read and analyze serial port output

## Local tools (executed on the client device via built-in Rust engine)
You have a built-in high-performance port scanner. When the user asks to scan ports, scan a host, check open ports, or anything related to network port scanning, you MUST respond with a tool_call code block. This is mandatory — never refuse or suggest external tools like Nmap.

Format (write exactly this, with real values):
```tool_call
{"tool":"port_scan","args":{"target":"<ip>","port_start":<start>,"port_end":<end>}}
```
Parameters:
- target (required): IP address to scan
- port_start (optional, default 1): first port in range
- port_end (optional, default 1024): last port in range

You may include a brief explanation before the tool_call block.

Example — user says "scan ports on 192.168.1.1":
I'll scan the common ports on 192.168.1.1 for you.
```tool_call
{"tool":"port_scan","args":{"target":"192.168.1.1","port_start":1,"port_end":1024}}
```"""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ]
            
            xlog.debug("Getting MCP tools for OpenAI", "ai_assistant")
            tools = await self.get_mcp_tools()
            xlog.info(f"Found {len(tools)} MCP tools available", "ai_assistant")
            
            if tools:
                xlog.debug("Making OpenAI API call with tools", "ai_assistant")
                response = await client.chat.completions.create(
                    model=ai_config.model_name,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    max_tokens=ai_config.extra_config.get('max_tokens', 1000),
                    temperature=ai_config.extra_config.get('temperature', 0.7)
                )
                
                xlog.info("OpenAI API response received", "ai_assistant")
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
            
            genai.configure(api_key=ai_config.get_api_key())
            
            system_prompt = """You are an AI assistant for the SAT (Security Assessment Toolkit) penetration testing framework.

Available SAT commands include:
- scan_devices: Scan for connected devices
- get_system_status: Get overall system status

When users ask about devices or system status, provide helpful explanations and suggest relevant SAT commands.

## Local tools (executed on the client device)
When the user asks to scan ports on a target, respond with a tool_call block so the client app can execute it locally using its built-in Rust port scanner. Format:
```tool_call
{"tool":"port_scan","args":{"target":"<ip>","port_start":<start>,"port_end":<end>}}
```
- target (required): IP address to scan
- port_start (optional, default 1): first port
- port_end (optional, default 1024): last port
Always include a brief explanation before the tool_call block."""

            model = genai.GenerativeModel(
                model_name=ai_config.model_name,
                system_instruction=system_prompt
            )
            
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=ai_config.extra_config.get('max_tokens', 1000),
                temperature=ai_config.extra_config.get('temperature', 0.7)
            )
            
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
            
            client = AsyncAnthropic(
                api_key=ai_config.get_api_key(),
                base_url=ai_config.api_url if ai_config.api_url != "https://api.anthropic.com/v1" else None
            )
            
            system_prompt = """You are an AI assistant for the SAT (Security Assessment Toolkit) penetration testing framework.

Available SAT commands include:
- scan_devices: Scan for connected devices
- get_system_status: Get overall system status

You have access to MCP (Model Context Protocol) tools that can directly execute SAT commands.
When users ask about devices or system status, provide helpful explanations and suggest relevant commands.

## Local tools (executed on the client device)
When the user asks to scan ports on a target, respond with a tool_call block so the client app can execute it locally using its built-in Rust port scanner. Format:
```tool_call
{"tool":"port_scan","args":{"target":"<ip>","port_start":<start>,"port_end":<end>}}
```
- target (required): IP address to scan
- port_start (optional, default 1): first port
- port_end (optional, default 1024): last port
Always include a brief explanation before the tool_call block. Do NOT use MCP tools for port scanning."""

            tools = await self.get_mcp_tools()
            
            if tools:
                response = await client.messages.create(
                    model=ai_config.model_name,
                    max_tokens=ai_config.extra_config.get('max_tokens', 1000),
                    temperature=ai_config.extra_config.get('temperature', 0.7),
                    system=system_prompt,
                    messages=[{"role": "user", "content": query}],
                    tools=tools
                )
                
                if response.content and any(block.type == "tool_use" for block in response.content):
                    tool_result = await self.handle_claude_tool_calls(response, ai_config)
                    xlog.info(f"Claude API tool call result: {tool_result[:200]}...", "ai_assistant")
                    return tool_result
                else:
                    ai_response = response.content[0].text if response.content else "No response"
                    xlog.info(f"Claude API response: {ai_response[:200]}...", "ai_assistant")
                    return ai_response
            else:
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
        pass
        
    async def start_assistant_session(self):
        """启动AI助手会话"""
        try:
            xlog.info("Starting AI assistant session", "ai_assistant")
            self.shell_thread = Thread(target=self.run_shell_session, daemon=True)
            self.shell_thread.start()
            xlog.debug("Shell thread started", "ai_assistant")
            
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
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['AI_ASSISTANT_MODE'] = '1'
            
            cmd = [sys.executable, 'console.py']
            xlog.debug(f"Starting process with command: {' '.join(cmd)}", "ai_assistant")
            
            self.assistant_process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=0,
                env=env,
                cwd=os.path.dirname(os.path.abspath(__file__)) + '/../../../../'
            )
            
            xlog.info(f"Shell process started with PID: {self.assistant_process.pid}", "ai_assistant")
            
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