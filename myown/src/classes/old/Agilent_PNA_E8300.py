''' Driver for Rhode & Schwarz ZVA

Manual (Requires login and R&S approval): https://scdn.rohde-schwarz.com/ur/pws/dl_downloads/dl_common_library/dl_manuals/gb_1/z/zva_2/ZVA_ZVB_ZVT_OperatingManual_en_33.pdf
'''

from .vector_network_analyzer_ctg import *
from .SimpleLoadpullConfig import ZVAConfig
from .TestConfig import *

class Agilent_PNA_E8300(VectorNetworkAnalyzerCtg1):
	
	SWEEP_CONTINUOUS = "sweep-continuous"
	SWEEP_SINGLE = "sweep-single"
	SWEEP_OFF = "sweep-off"
	
	def __init__(self, address:str):
		super().__init__(address, expected_idn="Agilent Technologies,E8361C")
		
		self.trace_lookup = {}
		
		self.measurement_codes = {}
		self.measurement_codes[VectorNetworkAnalyzerCtg1.MEAS_S11] = "S11"
		self.measurement_codes[VectorNetworkAnalyzerCtg1.MEAS_S12] = "S12"
		self.measurement_codes[VectorNetworkAnalyzerCtg1.MEAS_S21] = "S21"
		self.measurement_codes[VectorNetworkAnalyzerCtg1.MEAS_S22] = "S22"
	
	def set_freq_start(self, f_Hz:float, channel:int=1):
		self.write(f"SENS{channel}:FREQ:STAR {f_Hz}")
	def get_freq_start(self, channel:int=1):
		return float(self.query(f"SENS{channel}:FREQ:STAR?"))
	
	def set_freq_end(self, f_Hz:float, channel:int=1):
		self.write(f"SENS{channel}:FREQ:STOP {f_Hz}")
	def get_freq_end(self, channel:int=1):
		return float(self.query(f"SENS{channel}:FREQ:STOP?"))

	def set_freq_cw(self, f_Hz:float, channel:int=1):
		self.write(f"SENS{channel}:FREQ:CW {f_Hz}")
	def get_freq_cw(self, channel:int=1):
		return float(self.query(f"SENS{channel}:FREQ:CW?"))
	
	def set_power(self, p_dBm:float, channel:int=1, port:int=1):
		self.write(f"SOUR{channel}:POW{port}:LEV:IMM:AMPL {p_dBm}")
	def get_power(self, channel:int=1, port:int=1):
		return float(self.query(f"SOUR{channel}:POW{port}:LEV:IMM:AMPL?"))
	def power_off(self, channel:int=1, port:int=1):
		self.write(f"SOUR{channel}:POW{port}:MODE OFF")
	def power_on(self, channel:int=1, port:int=1):
		self.write(f"SOUR{channel}:POW{port}:MODE ON")
	
	def set_num_points(self, points:int, channel:int=1):
		self.write(f"SENS{channel}:SWEEP:POIN {points}")
	def get_num_points(self, channel:int=1):
		return int(self.query(f"SENS{channel}:SWEEP:POIN?"))
	
	def set_res_bandwidth(self, rbw_Hz:float, channel:int=1):
		self.write(f"SENS{channel}:BAND:RES {rbw_Hz}")
	def get_res_bandwidth(self, channel:int=1):
		return float(self.query(f"SENS{channel}:BAND:RES?"))
	
	def set_rf_enable(self, enable:bool):
		self.write(f"OUTP:STAT {bool_to_ONFOFF(enable)}")
	def get_rf_enable(self):
		return str_to_bool(self.query(f"OUTP:STAT?"))
	
	def clear_traces(self):
		self.write(f"CALC:PAR:DEL:ALL")
	
	def add_trace(self, channel:int, trace:int, measurement:str):
		
		# Get measurement code
		try:
			meas_code = self.measurement_codes[measurement]
		except:
			print(f"Unrecognized measurement!")
			return
		
		# Check that trace doesn't already exist
		if trace in self.trace_lookup.keys():
			print(f"Cannot add trace. Trace number {trace} already exists.")
		
		# Create name and save
		trace_name = f"trace{trace}"
		self.trace_lookup[trace] = trace_name
		
		# Create measurement - will not display yet
		self.write(f"CALC{channel}:PAR:DEF '{trace_name}', {meas_code}")
		
		# Create a trace and assoc. with measurement
		self.write(f"DISP:WIND:TRAC{trace}:FEED '{trace_name}'")
	
	def send_update_display(self):
		self.write(f"SYSTEM:DISPLAY:UPDATE ONCE")
	
	def get_trace_data_raw(self, trace:int, channel:int=1):
		'''
		
		Channel Data:
			* x: X data list (float)
			* y: Y data list (float)
			* x_units: Units of x-axis
			* y_units: UNits of y-axis
		'''
		
		# print(f"Binary transfer not implemented. Defaulting to slower ASCII.")
		self.write(f"CALCULATE{channel}:PAR:MNUM {trace}")
		self.write(f"CALCULATE{channel}:FORMAT REAL")
		real_data = self.query(f"CALC{channel}:DATA? FDATA")
		self.write(f"CALCULATE{channel}:FORMAT IMAG")
		imag_data = self.query(f"CALC{channel}:DATA? FDATA")
		try:
			real_tokens = real_data.split(",")
			imag_tokens = imag_data.split(",")
			return np.array([complex(float(re), float(im)) for re, im in zip(real_tokens, imag_tokens)])
		except:
			print("wrong")
		
		# # Get frequency range
		# f0 = self.get_freq_start()
		# fe = self.get_freq_end()
		# fnum = self.get_num_points()
		# freqs_Hz = list(np.linspace(f0, fe, fnum))
		
		# return {'x': freqs_Hz, 'y': trace, 'x_units': 'Hz', 'y_units': 'Reflection (complex), unitless'}

	def init_loadpull(self, channel = '1'):
		
		# write to zva example: CALCulate1:PARameter:DEFine 'Trc3', 'A1D1'
		# manual has how to do external generator also. I am pretty sure these are returned as voltages but that needs to be confirmed
		self.clear_traces()

		self.write("CALC" + str(channel) + ":PARameter:DEFine 'input_awave_trace', r1, 1")
		self.write(f"DISP:WIND:TRAC1:FEED 'input_awave_trace'")
		time.sleep(.1)
		self.write("CALC" + str(channel) + ":PARameter:DEFine 'output_awave_trace', r2, 1")
		self.write(f"DISP:WIND:TRAC2:FEED 'output_awave_trace'")
		time.sleep(.1)
		self.write("CALC" + str(channel) + ":PARameter:DEFine 'input_bwave_trace', a, 1")
		self.write(f"DISP:WIND:TRAC3:FEED 'input_bwave_trace'")
		time.sleep(.1)
		self.write("CALC" + str(channel) + ":PARameter:DEFine 'output_bwave_trace', b, 1")
		self.write(f"DISP:WIND:TRAC4:FEED 'output_bwave_trace'")
		time.sleep(.1)
		self.write("CALC" + str(channel) + ":PARameter:DEFine 's11', S11, 1")
		self.write(f"DISP:WIND:TRAC5:FEED 's11'")
		time.sleep(.1)

		self.write("INIT:CONT ON")

	def get_loadpull_data(self, channel = '1'):
		'''
		Determines Channel and Trace data as defined above. Can be overwritten. Channel must contain power and enriched wave call.
		'''
		self.write("INIT:CONT OFF")	
		temp = {'input_awave': self.get_trace_data('input_awave_trace', channel), 
				'output_awave': self.get_trace_data('output_awave_trace', channel), 
				'input_bwave': self.get_trace_data('input_bwave_trace', channel), 
				'output_bwave': self.get_trace_data('output_bwave_trace', channel)}
		self.write("INIT:CONT ON")
		return temp

	def get_trace_data(self, tracename:str, channel = '1'):
		
		# print(f"Binary transfer not implemented. Defaulting to slower ASCII.")
		
		self.write("CALC" + str(channel) + ":PAR:SEL '" + tracename + "'")
		self.write(f"CALCULATE{channel}:FORMAT REAL")
		time.sleep(.1)
		real_data = self.query(f"CALC{channel}:DATA? FDATA")
		self.write(f"CALCULATE{channel}:FORMAT IMAG")
		time.sleep(.1)
		imag_data = self.query(f"CALC{channel}:DATA? FDATA")
		self.write(f"CALCULATE{channel}:FORMAT MLOG")
		time.sleep(.1)
		dBm_data = self.query(f"CALC{channel}:DATA? FDATA")
		real_tokens = list(map(float,real_data.replace("\n", "").split(",")))
		imag_tokens = list(map(float,imag_data.replace("\n", "").split(",")))
		dBm_tokens = list(map(float,dBm_data.replace("\n", "").split(",")))

		# Get frequency range
		freqs_Hz = float(self.get_freq_cw())
		return {'trace_name': tracename ,'x': freqs_Hz, 'y_real': real_tokens, 'y_imag': imag_tokens, 
		  'dBm_mag': dBm_tokens}    