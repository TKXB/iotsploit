#
# Generated by erpcgen 1.12.0 on Sun Nov 17 17:46:17 2024.
#
# AUTOGENERATED - DO NOT EDIT
#

import erpc
from . import common, interface
# import callbacks declaration from other groups

# Client for APService
class APServiceClient(interface.IAPService):
    def __init__(self, manager):
        super(APServiceClient, self).__init__()
        self._clientManager = manager

    def getApList(self):
        # Build remote function invocation message.
        request = self._clientManager.create_request()
        codec = request.codec
        codec.start_write_message(erpc.codec.MessageInfo(
                type=erpc.codec.MessageType.kInvocationMessage,
                service=self.SERVICE_ID,
                request=self.GETAPLIST_ID,
                sequence=request.sequence))

        # Send request and process reply.
        self._clientManager.perform_request(request)
        _n0 = codec.start_read_list()
        _result = []
        for _i0 in range(_n0):
            _v0 = common.APInfo()._read(codec)
            _result.append(_v0)

        return _result


