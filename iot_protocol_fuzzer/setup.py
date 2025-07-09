from setuptools import setup

setup(
    name="iot-protocol-fuzzer",
    version="0.1.0",
    author="IoT Security Research",
    description="A modular fuzzing framework for IoT communication protocols",
    packages=[
        "iot_protocol_fuzzer",
        "iot_protocol_fuzzer.core",
        "iot_protocol_fuzzer.generators",
        "iot_protocol_fuzzer.harnesses",
        "iot_protocol_fuzzer.interfaces",
        "iot_protocol_fuzzer.monitoring",
        "iot_protocol_fuzzer.analysis",
        "iot_protocol_fuzzer.examples",
    ],
    package_dir={"iot_protocol_fuzzer": "."},
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Security",
        "Topic :: Software Development :: Testing",
    ],
    python_requires=">=3.7",
    install_requires=[
        "typing_extensions",
    ],
    extras_require={
        "can": ["python-can"],
        "uart": ["pyserial"],
        "spi": ["spidev"],
        "all": ["python-can", "pyserial", "spidev"],
    },
    include_package_data=True,
    package_data={
        "iot_protocol_fuzzer": ["examples/*.py", "examples/README.md"],
    },
) 