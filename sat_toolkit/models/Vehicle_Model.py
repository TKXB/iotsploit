import logging
from pydantic import BaseModel, ValidationError, conint, constr, IPvAnyAddress, model_validator
from typing import List, Optional, Union, Literal

logger = logging.getLogger(__name__)
logger.warning(
    "DEPRECATION WARNING: Vehicle_Model.py will be removed in a future version. "
    "This module has been superseded by Target_Model.py. "
    "Please update your code to use the new implementation."
)

# 示例数据
car_data = {
    "vin": "1HGCM82633A123456",
    "brand": "Honda",
    "model": "Accord",
    "year": 2020,
    "ecus": [
        {
            "name": "ECU1",
            "ip_address": "192.168.0.1",
            "can_id": 123,
            "pin": "1234",
            "description": "Engine Control Unit",
            "adb_version": "1.0.41",
            "os": "Android",
            "ecu_type": "DHU"
        },
        {
            "name": "ECU2",
            "ip_address": "192.168.0.2",
            "can_id": 456,
            "pin": "5678",
            "description": "Transmission Control Unit",
            "wifi_standard": "802.11ac",
            "os": "Linux",
            "ecu_type": "TBOX"
        },
        {
            "name": "ECU3",
            "ip_address": "192.168.0.3",
            "can_id": 789,
            "pin": "91011",
            "description": "Generic Control Unit",
            "os": "RTOS",
            "ecu_type": "Generic"
        }
    ]
}


class ECUBase(BaseModel):
    name: str                                # Name of the ECU
    ip_address: IPvAnyAddress                # IP address of the ECU
    can_id: conint(gt=0)                     # CAN ID of the ECU
    pin: constr(min_length=4, max_length=8)  # PIN must be between 4 and 8 characters
    description: Optional[str] = None        # Description of the ECU
    os: Optional[str] = None                 # Operating system of the ECU
    ecu_type: Literal['DHU', 'TBOX', 'Generic']  # Specifies the type of ECU


class DHU(ECUBase):
    adb_version: Optional[str] = None  # ADB version


class TBOX(ECUBase):
    wifi_standard: Optional[str] = None  # WiFi standard, e.g., "802.11ac"


class GenericECU(ECUBase):
    pass  # No additional fields


class Car(BaseModel):
    vin: constr(min_length=17, max_length=17)  # VIN must be 17 characters long
    brand: str                                # Brand of the car
    model: str                                # Model of the car
    year: conint(gt=1885)                     # Year of the car, must be greater than 1885
    ecus: List[Union[DHU, TBOX, GenericECU]]  # List of ECUs

    @model_validator(mode='before')
    def validate_ecus(cls, values):
        ecus = values.get('ecus', [])
        converted_ecus = []
        for idx, ecu in enumerate(ecus):
            ecu_type = ecu.get('ecu_type')
            if ecu_type == 'DHU':
                converted_ecus.append(DHU(**ecu))
            elif ecu_type == 'TBOX':
                converted_ecus.append(TBOX(**ecu))
            elif ecu_type == 'Generic':
                converted_ecus.append(GenericECU(**ecu))
            else:
                raise ValueError(f"ECU at index {idx} has an unknown type {ecu_type}")
        values['ecus'] = converted_ecus
        return values


if __name__ == '__main__':
    # test
    try:
        car = Car(**car_data)
        print(car)
        print(car.ecus[0].ip_address)
        
        # 检查每个ECU的类型并打印类型信息
        for ecu in car.ecus:
            if isinstance(ecu, DHU):
                print(f"{ecu.name} is a DHU with ADB version: {ecu.adb_version}")
            elif isinstance(ecu, TBOX):
                print(f"{ecu.name} is a TBOX with WiFi standard: {ecu.wifi_standard}")
            elif isinstance(ecu, GenericECU):
                print(f"{ecu.name} is a Generic ECU")
        
    except ValidationError as e:
        print(e.json())
