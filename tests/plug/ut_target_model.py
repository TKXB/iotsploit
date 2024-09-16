import sys
import os
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from sat_toolkit.models.Target_Model import (
    TargetManager, Vehicle, Component, Interface,
    Vehicle, ComponentModel, InterfaceModel, Base
)

class TestTargetModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a new database for testing
        cls.db_path = os.path.join(os.path.dirname(__file__), 'test_target_database.sqlite')
        cls.engine = create_engine(f'sqlite:///{cls.db_path}', echo=False)
        Base.metadata.create_all(cls.engine)

    def setUp(self):
        self.target_manager = TargetManager()
        self.target_manager.engine = self.engine
        self.target_manager.Session = sessionmaker(bind=self.engine)
        self.target_manager.register_target("vehicle", Vehicle)
        
        # Clear the database before each test
        session = self.target_manager.Session()
        session.query(Vehicle).delete()
        session.query(ComponentModel).delete()
        session.query(InterfaceModel).delete()
        session.commit()
        session.close()

    @classmethod
    def tearDownClass(cls):
        # Remove the test database file
        os.remove(cls.db_path)

    def test_create_benz_target(self):
        benz_data = {
            "target_id": "benz_001",
            "name": "Mercedes-Benz E-Class",
            "type": "sedan",
            "ip_address": "192.168.1.100",
            "location": "Garage A",
            "properties": {
                "model_year": 2023,
                "engine": "3.0L Inline-6 Turbo"
            },
            "components": [
                {
                    "component_id": "comp_001",
                    "name": "MBUX Infotainment System",
                    "type": "infotainment",
                    "properties": {
                        "screen_size": "12.3 inches",
                        "software_version": "NTG 7.0"
                    }
                }
            ],
            "interfaces": [
                {
                    "interface_id": "intf_001",
                    "name": "OBD-II",
                    "type": "diagnostic",
                    "properties": {
                        "protocol": "CAN"
                    }
                }
            ]
        }

        benz = self.target_manager.create_target("vehicle", **benz_data)
        
        self.assertIsInstance(benz, Vehicle)
        self.assertEqual(benz.target_id, "benz_001")
        self.assertEqual(benz.name, "Mercedes-Benz E-Class")
        self.assertEqual(benz.type, "sedan")
        self.assertEqual(benz.properties["model_year"], 2023)
        self.assertEqual(benz.properties["engine"], "3.0L Inline-6 Turbo")
        
        self.assertEqual(len(benz.components), 1)
        self.assertIsInstance(benz.components[0], Component)
        self.assertEqual(benz.components[0].name, "MBUX Infotainment System")
        
        self.assertEqual(len(benz.interfaces), 1)
        self.assertIsInstance(benz.interfaces[0], Interface)
        self.assertEqual(benz.interfaces[0].name, "OBD-II")

        # Check if the vehicle is saved in the database
        session = self.target_manager.Session()
        db_vehicle = session.query(Vehicle).filter_by(target_id="benz_001").first()
        self.assertIsNotNone(db_vehicle)
        self.assertEqual(db_vehicle.name, "Mercedes-Benz E-Class")
        session.close()

    def test_create_bmw_target(self):
        bmw_data = {
            "target_id": "bmw_001",
            "name": "BMW X5",
            "type": "SUV",
            "ip_address": "192.168.1.101",
            "location": "Garage B",
            "properties": {
                "model_year": 2023,
                "engine": "3.0L TwinPower Turbo inline-6"
            },
            "components": [
                {
                    "component_id": "comp_001",
                    "name": "iDrive System",
                    "type": "infotainment",
                    "properties": {
                        "screen_size": "12.3 inches",
                        "software_version": "8.0"
                    }
                }
            ],
            "interfaces": [
                {
                    "interface_id": "intf_001",
                    "name": "BMW Connected Drive",
                    "type": "telematics",
                    "properties": {
                        "connectivity": "4G LTE"
                    }
                }
            ]
        }

        bmw = self.target_manager.create_target("vehicle", **bmw_data)
        
        self.assertIsInstance(bmw, Vehicle)
        self.assertEqual(bmw.target_id, "bmw_001")
        self.assertEqual(bmw.name, "BMW X5")
        self.assertEqual(bmw.type, "SUV")
        self.assertEqual(bmw.properties["model_year"], 2023)
        self.assertEqual(bmw.properties["engine"], "3.0L TwinPower Turbo inline-6")
        
        self.assertEqual(len(bmw.components), 1)
        self.assertIsInstance(bmw.components[0], Component)
        self.assertEqual(bmw.components[0].name, "iDrive System")
        
        self.assertEqual(len(bmw.interfaces), 1)
        self.assertIsInstance(bmw.interfaces[0], Interface)
        self.assertEqual(bmw.interfaces[0].name, "BMW Connected Drive")

        # Check if the vehicle is saved in the database
        session = self.target_manager.Session()
        db_vehicle = session.query(Vehicle).filter_by(target_id="bmw_001").first()
        self.assertIsNotNone(db_vehicle)
        self.assertEqual(db_vehicle.name, "BMW X5")
        session.close()

    def test_get_all_vehicles(self):
        # Create two vehicles
        self.target_manager.create_target("vehicle", target_id="v001", name="Car 1", type="sedan")
        self.target_manager.create_target("vehicle", target_id="v002", name="Car 2", type="SUV")

        # Retrieve all vehicles
        all_vehicles = self.target_manager.get_all_vehicles()

        self.assertEqual(len(all_vehicles), 2)
        self.assertEqual(all_vehicles[0]["name"], "Car 1")
        self.assertEqual(all_vehicles[1]["name"], "Car 2")

if __name__ == '__main__':
    unittest.main()