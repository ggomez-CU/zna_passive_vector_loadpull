""" Keysight 8360L Series Swept CW Generator
"""

from .TestConfig import *
import numpy as np
from pylogfile.base import *
from scipy.io import loadmat

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

class SystemValidationPowerConfig(TestConfig):

	def __init__(self, config_file:str, Z0 = 50):
		super().__init__(config_file, log=None)

		self.Z0 = Z0
		self.frequency = [float(num) for num in self.config_file_json["Frequency"]]
		self.input_power_dBm = [float(num) for num in self.config_file_json["Input Power (dBm)"]]
		self.sweep_type = self.config_file_json["Sweep Type"].lower()

		self.error_directivity = self.get_error_mat(self.config_file_json["Files"]["Error Term 22 EDir"])
		self.error_tracking = self.get_error_mat(self.config_file_json["Files"]["Error Term 22 ERft"])
		self.error_match = self.get_error_mat(self.config_file_json["Files"]["Error Term 22 ESrm"])
		self.error_frequencies =  self.get_freq_mat(self.config_file_json["Files"]["Error Term 22 ESrm"])
		
		self.output_IL = self.get_IL_mat(self.config_file_json["Files"]["Output Sparam IL (dB)"])
		self.thru_IL = self.get_IL_mat(self.config_file_json["Files"]["Thru Sparam IL (dB)"])
		self.input_IL = self.get_IL_mat(self.config_file_json["Files"]["Input Sparam IL (dB)"])
		self.output_coupling = self.get_IL_mat(self.config_file_json["Files"]["Output Coupling (dB)"])
		self.input_coupling = self.get_IL_mat(self.config_file_json["Files"]["Input Coupling (dB)"])
		self.freqs_IL = self.config_file_json["Files"]["IL Freqs"]


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

	def get_error_terms_freq(self, freq):
		try:
			idx = self.get_freq_index(freq)
			return {'directivity': self.error_directivity[idx], 
					'tracking': self.error_tracking[idx], 
					'match': self.error_match[idx]}
		except Exception as e:
			# print(f"Exception: {e}")
			return {'directivity': 1, 
					'tracking': 1, 
					'match': 1}

	def get_freq_index(self,freq,case=1):
		# Case 1 is error case 2 is compensation. freq is GHz
		if case == 1:
			return int(np.where(np.round(self.error_frequencies/1e9,3) == freq)[0][0])
		if case == 2:
			return int(np.where(np.round(self.freqs_IL,3) == freq)[0][0])

	def get_error_mat(self,file):
		filedata = np.genfromtxt(file, delimiter=" ")
		return np.array([complex(float(re), float(im)) for re, im in zip(filedata[:,1], filedata[:,2])])

	def get_freq_mat(self,file):
		filedata = np.genfromtxt(file, delimiter=" ")
		return np.array([float(x) for x in filedata[:,0]])

	def get_IL_mat(self,file):
		try:
			mat_data = loadmat(file)
			temp = mat_data[list(mat_data.keys())[-1]]
			return [x[0] for x in temp]
		except Exception as e:
			print(f"Exception: {e}")
			# pass

	def get_comp_freq(self, freq):
		try:
			idx = self.get_freq_index(freq,2)
			return {'output IL': self.output_IL[idx], 
					'input IL': self.input_IL[idx], 
					'output coupling': self.output_coupling[idx], 
					'input coupling': self.input_coupling[idx]}
		except Exception as e:
			# print(f"Exception: {e}")
			return {'output IL': 1, 
					'input IL': 1, 
					'output coupling': 1, 
					'input coupling': 1}
