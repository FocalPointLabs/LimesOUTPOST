import json
import os
from jsonschema import validate, ValidationError
from limes_outpost.utils.logger import LimesOutpostLogger

class ContractValidator:
    def __init__(self, contract_dir=None):
        if contract_dir is None:
            import pathlib
            contract_dir = str(
                pathlib.Path(__file__).parent.parent / "contracts"
            )
        self.contract_dir = contract_dir
        self.logger = LimesOutpostLogger()

    def check(self, data, contract_name):
        """
        The 'Handshake' check.
        Returns the original data if valid, raises exception if not.
        """
        contract_path = os.path.join(self.contract_dir, f"{contract_name}.json")
        
        if not os.path.exists(contract_path):
            self.logger.error(f"⚠️ CRITICAL: Contract '{contract_name}' missing.")
            raise FileNotFoundError(f"Contract {contract_name} is missing.")

        try:
            with open(contract_path, 'r') as f:
                schema = json.load(f)
            
            # Perform validation
            validate(instance=data, schema=schema)
            
            # Return the data so the Agent can pass it to the next step
            return data 

        except ValidationError as e:
            # Enhanced Error Logging: Tell us EXACTLY where the JSON failed
            path = " -> ".join([str(p) for p in e.path]) if e.path else "root"
            error_msg = f"Field: {path} | Error: {e.message}"
            self.logger.error(f"❌ CONTRACT BREACH in [{contract_name}]: {error_msg}")
            raise Exception(f"Data failed contract '{contract_name}': {error_msg}")
            
        except json.JSONDecodeError:
            self.logger.error(f"📂 Contract file '{contract_name}.json' is corrupted.")
            raise