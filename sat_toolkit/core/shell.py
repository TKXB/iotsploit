from plugin_manager import ExploitPluginManager


def main():
    manager = ExploitPluginManager()
    manager.initialize()
    target = {
    'ip': '192.168.50.64',
    'user': 'username',
    'passwd': 'password',
    'cmd': 'ls -l'
    }
    manager.exploit(target)

# Example usage:
if __name__ == "__main__":
    main()