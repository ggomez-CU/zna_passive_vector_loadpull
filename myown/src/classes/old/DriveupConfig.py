""" Keysight 8360L Series Swept CW Generator

Manual: http://www.doe.carleton.ca/~nagui/labequip/synth/manuals/e4400324.pdf
"""

from .TestConfig import *
import numpy as np
from pylogfile.base import *

# from heimdallr.base import *
# from heimdallr.instrument_control.categories.rf_signal_generator_ctg import *

#I think importanting different classes is going to be a pain. maybe do the pip install -e in readme...?

class ZVAConfig():

	def __init__(self, IP_address, input_port, output_port):
		self.IP_address = IP_address
		self.input_port = input_port
		self.output_port = output_port

class LoadtunerConfig():
	def __init__(self, IP_address, timeout, port, printstatements):
		self.IP_address = IP_address
		self.timeout = timeout
		self.port = port
		self.printstatements = printstatements

class DriveupConfig(TestConfig):

	def __init__(self, config_file:str, log:LogPile, Z0 = 50):
		super().__init__(config_file, log)

		self.Z0 = Z0
		self.frequency = [float(num) for num in self.config_file_json["Frequency"]]
		self.input_power_dBm = [float(num) for num in self.config_file_json["Input Power (dBm)"]]

		self.ZVA_config = ZVAConfig(self.config_file_json["ZVA40"]["IP address"],
							    self.config_file_json["ZVA40"]["Input port"],
								self.config_file_json["ZVA40"]["Output port"])

		self.loadtuner_config = LoadtunerConfig(self.config_file_json["Load Tuner"]["IP address"],
										   self.config_file_json["Load Tuner"]["Timeout"],
										   self.config_file_json["Load Tuner"]["Port"],
										   self.config_file_json["Load Tuner"]["Print Statements"])
