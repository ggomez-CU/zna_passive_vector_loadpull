from pylogfile.base import *

class TestConfig:

    def __init__(self, config_file:str, log:LogPile ):
        """
        Test configuration class. 

        Parameters
        ----------
        config_file: A string containing the location and file name of the configuration file for the test
        """
        
        self.config_file = config_file
        with open(self.config_file, 'r') as file:
            self.config_file_json =  json.load(file)  
        