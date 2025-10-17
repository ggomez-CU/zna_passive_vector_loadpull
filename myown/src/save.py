import os
from datetime import datetime
from configClass import configClass

class saveClass():

	def __init__(self, configClass):
        self.now = datetime.now().strftime("%Y-%m-%d_%H_%M")
        self.date = datetime.now().strftime("Date-%Y-%m-%d")
        self.upper_output_dir = f"{os.getcwd()}\\data\\{configClass.testtype}\\{self.date}\\Test_{self.now}"
        os.mkdir(self.upper_output_dir)

        config_filepath = self.upper_output_dir + "\\config_file.json"

    def output_file_test_config_data(self, output_file, config_file, now, comments='None'):

        data = ({"Date and Time": self.now})
        data.update({"Comments": comments})
        data.update({"Configuration": config_file.config_file_json})

        with open(output_file, 'w') as f:
            json.dump(data, f, indent = 4)
            return data
    
    def mkloopfolder(self):
        
