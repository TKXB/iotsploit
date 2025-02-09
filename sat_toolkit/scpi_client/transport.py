import abc
import socket
import serial

class ScpiTransport(abc.ABC):
    @abc.abstractmethod
    def connect(self):
        pass

    @abc.abstractmethod
    def write(self, data: bytes) -> int:
        pass

    @abc.abstractmethod
    def read(self, bufsize: int = 1024) -> bytes:
        pass

    @abc.abstractmethod
    def flush(self):
        pass

    @abc.abstractmethod
    def close(self):
        pass

class ScpiTcpTransport(ScpiTransport):
    def __init__(self, ip: str, port: int, timeout: float = 5.0):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.sock = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.ip, self.port))

    def write(self, data: bytes) -> int:
        if not self.sock:
            raise ConnectionError("TCP socket is not connected")
        return self.sock.send(data)

    def read(self, bufsize: int = 1024) -> bytes:
        if not self.sock:
            raise ConnectionError("TCP socket is not connected")
        return self.sock.recv(bufsize)

    def flush(self):
        # TCP sockets usually do not need an explicit flush operation.
        pass

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None

class ScpiSerialTransport(ScpiTransport):
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None

    def connect(self):
        self.ser = serial.Serial(port=self.port,
                                 baudrate=self.baudrate,
                                 timeout=self.timeout)

    def write(self, data: bytes) -> int:
        if not self.ser:
            raise ConnectionError("Serial port is not connected")
        return self.ser.write(data)

    def read(self, bufsize: int = 1024) -> bytes:
        if not self.ser:
            raise ConnectionError("Serial port is not connected")
        return self.ser.read(bufsize)

    def flush(self):
        if self.ser:
            self.ser.flush()

    def close(self):
        if self.ser:
            self.ser.close()
            self.ser = None