import logging
from sat_toolkit.tools.net_audit_mgr import net_scan

logger.info("Now to scann 192.168.0.0/16")

net_scan.Instance().ip_detect("192.168.0.0/16")