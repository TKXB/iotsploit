import logging
from sat_toolkit.tools.net_audit_mgr import net_scan

logger.info("Now to scann 10.0.0.0/8")

net_scan.Instance().ip_detect("10.0.0.0/8")