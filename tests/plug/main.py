from mgr import NetworkPluginManager
import logging

def main():
    # 配置日志
    logging.basicConfig(level=logging.INFO)

    # 实例化插件管理器（插件会自动加载）
    plugin_manager = NetworkPluginManager()
        
    # SSH 示例
    ssh_context = plugin_manager.connect("ssh", "192.168.8.146", "sat", "123456")
    if ssh_context:
        res = plugin_manager.execute_command("ssh", ssh_context, "ls -l")
        print(res)
        plugin_manager.disconnect("ssh", ssh_context)

    # FTP 示例
    ftp_context = plugin_manager.connect("ftp", "192.168.8.148", "user", "password")
    if ftp_context:
        res = plugin_manager.execute_command("ftp", ftp_context, "NOOP")
        print(res)
        plugin_manager.disconnect("ftp", ftp_context)
    
    # Telnet 示例
    telnet_context = plugin_manager.connect("telnet", "192.168.8.147", "user", "password")
    if telnet_context:
        res = plugin_manager.execute_command("telnet", telnet_context, "ls -l")
        print(res)
        plugin_manager.disconnect("telnet", telnet_context)

if __name__ == "__main__":
    main()
