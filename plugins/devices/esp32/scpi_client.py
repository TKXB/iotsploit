import abc
import socket
import time

try:
    import serial
except ImportError:  # pragma: no cover - exercised only when pyserial is absent
    serial = None


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
        if serial is None:
            raise ImportError("pyserial is required to use ScpiSerialTransport")
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            timeout=self.timeout,
        )

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


class ScpiClient:
    def __init__(self, transport):
        """
        transport must be an instance of ScpiTransport (or subclass)
        """
        self.transport = transport

    def connect(self):
        self.transport.connect()

    def send_command(self, command: str, terminator: str = "\n") -> None:
        full_command = command.strip() + terminator
        self.transport.write(full_command.encode())
        self.transport.flush()

    def query(self, command: str, terminator: str = "\n", timeout: float = 2.0) -> str:
        """
        Send a SCPI query and wait for a response.
        """
        self.send_command(command, terminator)
        start_time = time.time()
        received_data = b""
        while time.time() - start_time < timeout:
            data = self.transport.read(1024)
            if data:
                received_data += data
                if received_data.endswith(terminator.encode()):
                    break
        return received_data.decode().strip()

    def reset(self) -> None:
        self.send_command("*RST")

    def get_status(self) -> str:
        return self.query("SYSTem:STATus?")

    def get_version(self) -> str:
        return self.query("SYSTem:VERSion?")

    def close(self):
        self.transport.close()
