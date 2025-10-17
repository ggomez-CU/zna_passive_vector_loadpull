''' Driver for Rhode & Schwarz ZVA

Manual (Requires login and R&S approval): https://scdn.rohde-schwarz.com/ur/pws/dl_downloads/dl_common_library/dl_manuals/gb_1/z/zva_2/ZVA_ZVB_ZVT_OperatingManual_en_33.pdf
'''

from .vector_network_analyzer_ctg import *
from .SimpleLoadpullConfig import ZVAConfig
from .TestConfig import *

class RohdeSchwarzZVA(VectorNetworkAnalyzerCtg1):
	
	SWEEP_CONTINUOUS = "sweep-continuous"
	SWEEP_SINGLE = "sweep-single"
	SWEEP_OFF = "sweep-off"
	
	def __init__(self, address:str, log:LogPile):
		super().__init__(address, log, expected_idn="Rohde&Schwarz,ZVA")
		
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
			self.log.error(f"Unrecognized measurement!")
			return
		
		# Check that trace doesn't already exist
		if trace in self.trace_lookup.keys():
			self.log.error(f"Cannot add trace. Trace number {trace} already exists.")
		
		# Create name and save
		trace_name = f"trace{trace}"
		self.trace_lookup[trace] = trace_name
		
		# Create measurement - will not display yet
		self.write(f"CALC{channel}:PAR:DEF '{trace_name}', {meas_code}")
		
		# Create a trace and assoc. with measurement
		self.write(f"DISP:WIND:TRAC{trace}:FEED '{trace_name}'")
	
	def send_update_display(self):
		self.write(f"SYSTEM:DISPLAY:UPDATE ONCE")
	
	def get_channel_data(self, channel:int):
		'''
		
		Channel Data:
			* x: X data list (float)
			* y: Y data list (float)
			* x_units: Units of x-axis
			* y_units: UNits of y-axis
		'''
		
		self.log.warning(f"Binary transfer not implemented. Defaulting to slower ASCII.")
		
		# # Check that trace exists
		# if trace not in self.trace_lookup.keys():
		# 	self.log.error(f"Trace number {trace} does not exist!")
		# 	return
		
		# trace_name = self.trace_lookup[trace]
		
		# # Select the specified measurement/trace
		# self.write(f"CALC{channel}:PAR:SEL {trace_name}")
		
		# # Set data format
		# self.write(f"FORM:DATA REAL,64")
		
		self.write(f"CALCULATE{channel}:FORMAT REAL")
		real_data = self.query(f"CALC{channel}:DATA? FDATA")
		self.write(f"CALCULATE{channel}:FORMAT IMAG")
		imag_data = self.query(f"CALC{channel}:DATA? FDATA")
		real_tokens = real_data.split(",")
		imag_tokens = imag_data.split(",")
		trace = [complex(float(re), float(im)) for re, im in zip(real_tokens, imag_tokens)]
		
		# Get frequency range
		f0 = self.get_freq_start()
		fe = self.get_freq_end()
		fnum = self.get_num_points()
		freqs_Hz = list(np.linspace(f0, fe, fnum))
		
		return {'x': freqs_Hz, 'y': trace, 'x_units': 'Hz', 'y_units': 'Reflection (complex), unitless'}

	def init_zva_subsix_loadpull(self, config_test:ZVAConfig, channel = '1', 
						input_awave_trace = 1, 
						input_bwave_trace = 2, 
						output_awave_trace = 3, 
						output_bwave_trace = 4,
						output_impedance = 5):
		
		# write to zva example: CALCulate1:PARameter:DEFine 'Trc3', 'A1D1'
		# manual has how to do external generator also. I am pretty sure these are returned as voltages but that needs to be confirmed

		self.write("CALC" + str(channel) + ":PARameter:SDEFine 'Trc" + str(input_awave_trace)
				+ "', 'A" + str(config_test.input_port)+ "'")
		time.sleep(.1)
		self.write("CALC" + str(channel) + ":PARameter:SDEFine 'Trc" + str(output_awave_trace) 
				+ "', 'A" + str(config_test.output_port) + "'")
		time.sleep(.1)
		self.write("CALC" + str(channel) + ":PARameter:SDEFine 'Trc" + str(input_bwave_trace) 
				+ "', 'B" + str(config_test.input_port) + "'")
		time.sleep(.1)
		self.write("CALC" + str(channel) + ":PARameter:SDEFine 'Trc" + str(output_bwave_trace) 
				+ "', 'B" + str(config_test.output_port) + "'")
		time.sleep(.1)
		self.write("CALC" + str(channel) + ":PARameter:SDEFine 'Trc" + str(output_impedance) 
				+ "', 'A" + str(config_test.output_port)  				
				+ "/B" + str(config_test.output_port) + "'")
		time.sleep(.1)

	def get_loadpull_data(self, channel = '1', 
						input_awave_trace = 1, 
						input_bwave_trace = 2, 
						output_awave_trace = 3, 
						output_bwave_trace = 4,
						output_impedance = 5):
		'''
		Determines Channel and Trace data as defined above. Can be overwritten. Channel must contain power and enriched wave call.
		'''
			
		return {'input_awave': self.get_trace_data(input_awave_trace, channel), 
				'input_bwave': self.get_trace_data(input_bwave_trace, channel), 
				'output_awave': self.get_trace_data(output_awave_trace, channel), 
				'output_bwave': self.get_trace_data(output_bwave_trace, channel),
				'output_impedance': self.get_trace_data(output_impedance, channel)}

	def get_trace_data(self, tracenumber:int, channel = '1'):
		
		self.log.warning(f"Binary transfer not implemented. Defaulting to slower ASCII.")
		
		trace_name = 'Trc' + str(tracenumber)
		self.write("CALC" + str(channel) + ":PAR:SEL '" + trace_name + "'")

		self.write(f"CALCULATE{channel}:FORMAT REAL")
		time.sleep(.1)
		real_data = self.query(f"CALC{channel}:DATA? FDATA")
		self.write(f"CALCULATE{channel}:FORMAT IMAG")
		time.sleep(.1)
		imag_data = self.query(f"CALC{channel}:DATA? FDATA")
		self.write(f"CALCULATE{channel}:FORMAT MLOG")
		time.sleep(.1)
		dBm_data = self.query(f"CALC{channel}:DATA? FDATA")
		self.write(f"CALCULATE{channel}:FORMAT MLIN")
		time.sleep(.1)
		mag = self.query(f"CALC{channel}:DATA? FDATA")
		self.write(f"CALCULATE{channel}:FORMAT PHAS")
		time.sleep(.1)
		phs = self.query(f"CALC{channel}:DATA? FDATA")
		real_tokens = list(map(float,real_data.replace("\n", "").split(",")))
		imag_tokens = list(map(float,imag_data.replace("\n", "").split(",")))
		mag_tokens = list(map(float,mag.replace("\n", "").split(",")))
		phs_tokens = list(map(float,phs.replace("\n", "").split(",")))
		dBm_tokens = list(map(float,dBm_data.replace("\n", "").split(",")))

		# Get frequency range
		freqs_Hz = float(self.get_freq_cw())
		return {'trace_name': trace_name ,'x': freqs_Hz, 'y_real': real_tokens, 'y_imag': imag_tokens, 
		  'dBm_mag': dBm_tokens, 'mag': mag_tokens, 'phase': phs_tokens, 
		  'x_units': 'Hz', 'y_units': 'EWC wave data (voltage)'}    