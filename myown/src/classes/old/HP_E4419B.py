from .power_meter_ctg import *

class HP_E4419B(PowerMeterCtg1):
	
	def __init__(self, address:str):
		super().__init__(address, expected_idn="Agilent Technologies,E4419B")
    
	def set_freq(self, f_Hz:float, channel:int=1):
		self.inst.write(f"SENSe{channel}:FREQuency {f_Hz}")
	
	def set_avg(self, points:int, channel:int=1):
		pass
	
	def set_bandwidth(self, rbw_Hz:float, channel:int=1):
		pass
	
	def get_power(self):
		return float(self.inst.query("MEAS?"))
	
	def fetch_power(self):
		return float(self.inst.query("MEAS?"))
	