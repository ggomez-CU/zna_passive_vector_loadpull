from .base import *

class PowerMeterCtg0(Driver):
	
	def __init__(self, address:str, expected_idn=""):
		super().__init__(address, expected_idn=expected_idn)

class PowerMeterCtg1(PowerMeterCtg0):
	
	def __init__(self, address:str, expected_idn=""):
		super().__init__(address,  expected_idn= expected_idn)
	
	def set_freq(self, f_Hz:float, channel:int=1):
		pass
	
	def set_avg(self, points:int, channel:int=1):
		pass
	
	def set_bandwidth(self, rbw_Hz:float, channel:int=1):
		pass
	
	def get_power(self):
		pass
	
	