''' Driver for Keysight 34400 series digital multimeters. 

https://www.keysight.com/us/en/assets/9018-03876/service-manuals/9018-03876.pdf?success=true 
'''

import array
from .base import *
from .dc_power_supply_ctg import *

class Keithly_2230(DCPowerSupplyCtg1):
	
	def __init__(self, address:str):
		super().__init__(address) 
		
		# Unit to make sure is matched by returned string
		self.check_units = ""

	def set_channel_on(self,channel):
		self.write(f"INST:NSEL {channel}")
		self.write(f"CHAN:OUTP ON")
	
	def set_channel_off(self,channel):
		self.write(f"INST:NSEL {channel}")
		self.write(f"CHAN:OUTP OFF")

	def set_channel(self, channel, voltage, current):
		self.write(f"APPL CH{channel}, {voltage}, {current}")
	
	def fetch_voltage_all(self):
		return list(map(float,self.query("FETCH:VOLT? ALL").replace("\n", "").split(",")))

	def get_voltage_all(self):
		return list(map(float,self.query("MEAS:VOLT? ALL").replace("\n", "").split(",")))

	def fetch_current_all(self):
		return list(map(float,self.query("FETCH:CURR? ALL").replace("\n", "").split(",")))

	def get_current_all(self):
		return list(map(float,self.query("MEAS:CURR? ALL").replace("\n", "").split(",")))
	
	def fetch_voltage(self, channel):
		return float(self.query(f"FETCH:VOLT? CH{channel}").replace("\n", ""))

	def get_voltage(self, channel):
		return float(self.query(f"MEAS:VOLT? CH{channel}").replace("\n", ""))

	def fetch_current(self, channel):
		return float(self.query(f"FETCH:CURR? CH{channel}").replace("\n", ""))

	def get_current(self, channel):
		return float(self.query(f"MEAS:CURR? CH{channel}").replace("\n", ""))