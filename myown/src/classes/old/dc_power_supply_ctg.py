from .base import *

class DCPowerSupplyCtg0(Driver):
	
	def __init__(self, address:str, expected_idn=""):
		super().__init__(address, expected_idn=expected_idn)

class DCPowerSupplyCtg1(DCPowerSupplyCtg0):
	
	def __init__(self, address:str, expected_idn=""):
		super().__init__(address, expected_idn=expected_idn)
	