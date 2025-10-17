""" Keysight 8360L Series Swept CW Generator
"""

from .TestConfig import *
import numpy as np
from pylogfile.base import *

# from heimdallr.base import *
# from heimdallr.instrument_control.categories.rf_signal_generator_ctg import *

#I think importanting different classes is going to be a pain. maybe do the pip install -e in readme...?

class PNAConfig():

	def __init__(self, IP_address, input_port, output_port):
		self.IP_address = IP_address
		self.input_port = input_port
		self.output_port = output_port

class LoadtunerConfig():

	def __init__(self, sn, timeout, port, printstatements, calfile:str):
		self.sn = sn
		self.timeout = timeout
		self.port = port
		self.printstatements = printstatements
		self.calfile = calfile

class SystemValidationConfig(TestConfig):

	def __init__(self, config_file:str, Z0 = 50):
		super().__init__(config_file, log=None)

		self.Z0 = Z0
		self.frequency = [float(num) for num in self.config_file_json["Frequency"]]
		self.sweep_type = self.config_file_json["Sweep Type"].lower()
		self.offset_complex = complex(self.config_file_json["Rectangular Offset [x,y]"][0],
									self.config_file_json["Rectangular Offset [x,y]"][1])

		self.PNA_config = PNAConfig(self.config_file_json["PNA"]["IP address"],
							    self.config_file_json["PNA"]["Input port"],
								self.config_file_json["PNA"]["Output port"])

		self.loadtuner_config = LoadtunerConfig(self.config_file_json["Load Tuner"]["Tuner SN"],
										   self.config_file_json["Load Tuner"]["Timeout"],
										   self.config_file_json["Load Tuner"]["Port"],
										   self.config_file_json["Load Tuner"]["Print Statements"],
                                           self.config_file_json["Load Tuner"]["Tuner Calibration File"])

		self.check_expected_config()

		self.sweep_type_config()

	def check_expected_config(self):

		#Check number of frequencies is 1 for simple loadpull
		if len(self.frequency) != 1:
			print("Incorrect number of frequencies defined in the test configuration file: " + self.config_file)
			print("For Simple Loadpull test only 1 frequency allowed")
			print("See README.md for more info")
			exit()

		if ( self.sweep_type != "gamma" and self.sweep_type != "Z" ):
			
			print("Incorrect Sweep Type defined in the test configuration file: " + self.config_file)
			print("For Simple Loadpull test sweep type are Gamma (sweeping defined by magnitude and phase inputs) or Z (impedances defined by real and imaginary components)")
			print("See README.md for more info")
			exit()

	def sweep_type_config(self):
		if self.sweep_type == "gamma":
			self.magnitude_list = self.config_file_json["Gamma Magnitude List"]
			self.phase_list = self.config_file_json["Gamma Phase List"]
			self.loadpoints = np.array([(M*np.exp(1j*phs/180*np.pi)) for M in self.magnitude_list for phs in self.phase_list])
			# self.loadpoints = np.array([(self.Z0 * ((1 + M*np.exp(phs)) / (1 - M*np.exp(phs)))) for M in self.magnitude_list for phs in self.phase_list])

		if self.sweep_type == "z":
			self.realZ_list = self.config_file_json["Real Impedance List"]
			self.imagZ_list = self.config_file_json["Imaginary Impedance List"]
			self.loadpoints = np.array([complex(R,X) for R in self.realZ_list for X in self.imagZ_list])
			# self.loadpoints = np.array([(self.Z0 * ((1 + M*np.exp(phs)) / (1 - M*np.exp(phs)))) for M in self.magnitude_list for phs in self.phase_list])
