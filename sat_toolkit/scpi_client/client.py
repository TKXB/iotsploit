import time

class ScpiClient:
    def __init__(self, transport):
        """
        transport must be an instance of ScpiTransport (or subclass)
        """
        self.transport = transport

    def connect(self):
        self.transport.connect()

    def send_command(self, command: str, terminator: str = '\n') -> None:
        # Ensure the command ends with the proper terminator
        full_command = command.strip() + terminator
        self.transport.write(full_command.encode())
        # Optionally flush if needed
        self.transport.flush()

    def query(self, command: str, terminator: str = '\n', timeout: float = 2.0) -> str:
        """
        Send a SCPI query and wait for a response.
        """
        self.send_command(command, terminator)
        start_time = time.time()
        received_data = b""
        # Buffers data until timeout reached
        while time.time() - start_time < timeout:
            data = self.transport.read(1024)
            if data:
                received_data += data
                # Optionally, you can break on a specific terminating sequence
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