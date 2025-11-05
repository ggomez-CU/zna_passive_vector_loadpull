import sys
from sys import platform
import matplotlib
import copy
from heimdallr.base import interpret_range
import ctypes
from jarnsaxa import *
matplotlib.use('qtagg')
from skrf import Network

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from pylogfile.base import *

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtGui import QAction, QActionGroup, QDoubleValidator, QIcon, QFontDatabase, QFont, QPixmap
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import QWidget, QTabWidget, QLabel, QGridLayout, QLineEdit, QCheckBox, QSpacerItem, QSizePolicy, QMainWindow, QSlider, QPushButton, QGroupBox, QListWidget, QFileDialog, QProgressBar, QStatusBar

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

import matplotlib.pyplot as plt
from chillyinductor.rp22_helper import *
from colorama import Fore, Style
from ganymede import *
from graf.base import *
from pylogfile.base import *
import sys
import numpy as np
import pickle
from matplotlib.widgets import Slider, Button
from abc import abstractmethod, ABC
import argparse

log = LogPile()
log.set_terminal_level("LOWDEBUG")

import matplotlib as mpl
mpl.rcParams['axes.formatter.useoffset'] = False

# TODO: Important
#
# * Tests show if only the presently displayed graph is rendered, when the sliders are adjusted, the update speed is far better (no kidding).
# * Tests also show pre-allocating a mask isn't super useful. It's mostly the matplotlib rendering that slows it down.

# TODO:
# 1. Init graph properly (says void and stuff)
# 2. Add labels to values on freq and power sliders
# 3. Add save log, save graph, zoom controls, etc.
# 5. Datatips
# 7. Data panel at bottom showing file stats:
#		- collection date, operator notes, file size, num points, open log in lumberjack button

# 8. Better way to load any data file
# 9. Option for linear axes on HG graph, get better intuition for impact of drop in power of fund.
# 10. Add calibration things - impact of S-parameters and new CE definitions based on power from SG or
# 	with better S-parameter loss calibration.
# 11. Add tabs to look at raw spectrum analyzer data rather than the spectral components.

# 9. Make filename label copyable
# 12. Make graph of total power - looks like the SG power isn't super well calibrated and jumps at frequency transitions!

# TODO: Graphs to add
# 1. Applied voltage, measured current, target current, estimated additional impedance.
# 2. Temperature vs time
#

parser = argparse.ArgumentParser()
# parser.add_argument('-h', '--help')
parser.add_argument('-s', '--subtle', help="Run without naming.", action='store_true')
parser.add_argument('-d', '--detail', help="Show log details.", action='store_true')
parser.add_argument('-t', '--theme', help="Change color theme.", action='store_true')
parser.add_argument('--autopathdetails', help="Print additional information for debugging which paths are found.", action='store_true')
cli_args = parser.parse_args()
# print(cli_args)
# print(cli_args.subtle)

if cli_args.detail:
	log.str_format.show_detail = True

def get_font(font_ttf_path):
	
	abs_path = os.path.abspath(font_ttf_path)
	
	font_id = QFontDatabase.addApplicationFont(abs_path)
	if font_id == -1:
		print(f"Failed to read font")
		return None
	
	return QFontDatabase.applicationFontFamilies(font_id)[0]

# chicago_ff = get_font("./assets/Chicago.ttf")
# chicago_12 = QFont(chicago_ff, 12)

class DataLoadingManager:
	''' Class from which MasterData populates itself. Reads data from disk when neccesary. Stores
	both S-parameter data and HDF sweep data.'''
	
	def __init__(self, log:LogPile, conf_file:str=None, main_window=None):
		
		self.log = log
		self.main_window = main_window
		
		self.use_legacy_peakdetect = False
		
		# Get conf data
		self.data_conf = {}
		if conf_file is None:
			conf_file = os.path.join(".", "hga_conf.json")
		self.load_conf(conf_file)
		
		# This mutex is used to protect sweep_data and sparam_data
		self.data_mtx = threading.Lock()
		
		# Dictionary s.t. key=filename, value=dict of data
		self.sweep_data = {}
		
		# Dictionary s.t. key=filename, value = dict of data
		self.sparam_data = {}
	
	def clear_data(self):
		''' Erases all loaded data, forcing data to be re-read from disk.'''
		self.sweep_data = {}
		self.sparam_data = {}
	
	def load_conf(self, conf_file:str):
		
		# Load json file
		try:
			with open(conf_file, 'r') as fh:
				self.data_conf = json.load(fh)
		except Exception as e:
			self.log.critical(f"Failed to load configuration file.", detail=f"{e}")
			return False
		
		# Evaluate each sweep source
		for dss in self.data_conf['sweep_sources']:
			
			#For each entry, evaluate wildcards and find actual path
			full_path = get_general_path(dss['path'], dos_id_folder=True, print_details=cli_args.autopathdetails, unix_vol_name="M6 T7S")
			
			# Write log
			name = dss['chip_name']
			track = dss['track']
			if full_path is None:
				self.log.error(f"Failed to find sweep data source for chip {name}, track {track}.")
			else:
				self.log.debug(f"Sweep data source identified for chip {name}, track {track}.", detail=f"Path = {full_path}")
			
			# Save full path string, or None for error
			dss['full_path'] = full_path
		
		# Evaluate each sparam source
		for dss in self.data_conf['sparam_sources']:
			
			#For each entry, evaluate wildcards and find actual path
			cryo_full_path = get_general_path(dss['cryostat_file'], dos_id_folder=True, print_details=cli_args.autopathdetails, unix_vol_name="M6 T7S")
			
			# Write log
			name = dss['chip_name']
			track = dss['track']
			if cryo_full_path is None:
				self.log.error(f"Failed to find s-parameter data source for chip {name}, track {track}.")
			else:
				self.log.debug(f"S-parameter data source identified for chip {name}, track {track}.", detail=f"Path = {full_path}")
			
			# Save full path string, or None for error
			dss['cryo_full_path'] = cryo_full_path
		
		return True
	
	def get_sweep_full(self, sweep_filename:str):
		
		# CHeck if file needs to be read
		read_file = False
		with self.data_mtx:
		
			self.log.lowdebug(f"DLM Checking if file '{sweep_filename}' is loaded.")
		
			# Load data from file if not already present
			if sweep_filename not in self.sweep_data:
				self.log.info(f"Loading sweep data from file: {sweep_filename}")
				read_file = True
		
		# Start thread to read file if requested
		if read_file:
			self.log.lowdebug(f"Creating thread to read file from disk.")
			
			if self.main_window is not None:
				self.main_window.status_bar.setLoadingFile(True)
				self.main_window.app.processEvents()
			
			self.data_mtx.acquire()
			self.import_thread = ImportSweepThread(self, sweep_filename)
			self.import_thread.taskFinished.connect(self.fileLoadFinished)
			self.import_thread.start()
			
		
		# Access and return data
		with self.data_mtx:
			
			self.log.lowdebug(f"Accessing loaded sweep.")
			
			# return data if in databank
			if sweep_filename in self.sweep_data:
				return self.sweep_data[sweep_filename]
	
	def get_sparam(self, sp_filename:str):
		
		# Check if file needs to be read
		read_file = False
		with self.data_mtx:
			
			# Load data from file if not already present
			if sp_filename not in self.sparam_data:
				self.log.info(f"Loading s-parameter data from file: {sp_filename}")
				read_file = True
		
		# Start thread to read file if requested
		if read_file:
			
			self.log.lowdebug(f"Creating thread to read file from disk.")
			
			if self.main_window is not None:
				self.main_window.status_bar.setLoadingSPFile(True)
				self.main_window.app.processEvents()
			
			self.data_mtx.acquire()
			self.import_thread = ImportSparamThread(self, sp_filename)
			self.import_thread.taskFinished.connect(self.spfileLoadFinished)
			self.import_thread.start()
		
		# Access and returnn data
		with self.data_mtx:
			
			self.log.lowdebug(f"Accessing loaded sweep.")
			
			# Return data if in databank
			if sp_filename in self.sparam_data:
				return self.sparam_data[sp_filename]
	
	def fileLoadFinished(self):
		
		if self.main_window is not None:
			self.main_window.status_bar.setLoadingFile(False)
			self.main_window.app.processEvents()
	
	def spfileLoadFinished(self):
		
		if self.main_window is not None:
			self.main_window.status_bar.setLoadingSPFile(False)
			self.main_window.app.processEvents()
	
	def import_sweep_file(self, sweep_filename:str):
		''' Imports sweep data into the DLM's sweep dict from file.'''
		
		self.log.lowdebug(f"Reading file from disk: {sweep_filename}")
		
		##--------------------------------------------
		# Read HDF5 File
		
		# Load data from file
		hdfdata = hdf_to_dict(sweep_filename, to_lists=False)
		
		##--------------------------------------------
		# Generate Mixing Products lists
		
		data_out = list_search_spectrum_peak_harms(hdfdata['dataset']['waveform_f_Hz'], hdfdata['dataset']['waveform_s_dBm'], hdfdata['dataset']['freq_rf_GHz']*1e9, nharms=3, scan_bw_Hz=500, harm_scan_points=7)
		
		if not self.use_legacy_peakdetect:
			hdfdata['dataset']['rf1'] = data_out[1][0]
			hdfdata['dataset']['rf2'] = data_out[1][1]
			hdfdata['dataset']['rf3'] = data_out[1][2]
			
			hdfdata['dataset']['freqmeas_rf1'] = data_out[0][0]
			hdfdata['dataset']['freqmeas_rf2'] = data_out[0][1]
			hdfdata['dataset']['freqmeas_rf3'] = data_out[0][2]
		else:
			hdfdata['dataset']['rf1'] = spectrum_peak_list(hdfdata['dataset']['waveform_f_Hz'], hdfdata['dataset']['waveform_s_dBm'], hdfdata['dataset']['freq_rf_GHz']*1e9)
			hdfdata['dataset']['rf2'] = spectrum_peak_list(hdfdata['dataset']['waveform_f_Hz'], hdfdata['dataset']['waveform_s_dBm'], hdfdata['dataset']['freq_rf_GHz']*2e9)
			hdfdata['dataset']['rf3'] = spectrum_peak_list(hdfdata['dataset']['waveform_f_Hz'], hdfdata['dataset']['waveform_s_dBm'], hdfdata['dataset']['freq_rf_GHz']*3e9)
			
			hdfdata['dataset']['freqmeas_rf1'] = []
			hdfdata['dataset']['freqmeas_rf2'] = []
			hdfdata['dataset']['freqmeas_rf3'] = []
			
		hdfdata['dataset']['rf1W'] = dBm2W(hdfdata['dataset']['rf1'])
		hdfdata['dataset']['rf2W'] = dBm2W(hdfdata['dataset']['rf2'])
		hdfdata['dataset']['rf3W'] = dBm2W(hdfdata['dataset']['rf3'])
		
		##-------------------------------------------
		# Calculate conversion efficiencies
		
		hdfdata['dataset']['total_power'] = hdfdata['dataset']['rf1W'] + hdfdata['dataset']['rf2W'] + hdfdata['dataset']['rf3W']
		hdfdata['dataset']['ce2'] = hdfdata['dataset']['rf2W']/hdfdata['dataset']['total_power']*100
		hdfdata['dataset']['ce3'] = hdfdata['dataset']['rf3W']/hdfdata['dataset']['total_power']*100
		
		##-------------------------------------------
		# Generate lists of unique conditions

		hdfdata['dataset']['unique_bias'] = np.unique(hdfdata['dataset']['requested_Idc_mA'])
		hdfdata['dataset']['unique_pwr'] = np.unique(hdfdata['dataset']['power_rf_dBm'])
		hdfdata['dataset']['unique_freqs'] = np.unique(hdfdata['dataset']['freq_rf_GHz'])
		
		
		##------------------------------------------
		# Calculate extra impedance
		
		# Estimate system Z
		expected_Z = hdfdata['dataset']['MFLI_V_offset_V'][1]/(hdfdata['dataset']['requested_Idc_mA'][1]/1e3) #TODO: Do something more general than index 1
		system_Z = hdfdata['dataset']['MFLI_V_offset_V']/(hdfdata['dataset']['Idc_mA']/1e3)
		hdfdata['dataset']['extra_z'] = system_Z - expected_Z
		
		hdfdata['dataset']['zs_extra_z'] = calc_zscore(hdfdata['dataset']['extra_z'])
		hdfdata['dataset']['zs_meas_Idc'] = calc_zscore(hdfdata['dataset']['Idc_mA'])
		
		##------------------------------------------
		# Generate Z-scores
		
		hdfdata['dataset']['zs_ce2'] = calc_zscore(hdfdata['dataset']['ce2'])
		hdfdata['dataset']['zs_ce3'] = calc_zscore(hdfdata['dataset']['ce3'])
		
		hdfdata['dataset']['zs_rf1'] = calc_zscore(hdfdata['dataset']['rf1'])
		hdfdata['dataset']['zs_rf2'] = calc_zscore(hdfdata['dataset']['rf2'])
		hdfdata['dataset']['zs_rf3'] = calc_zscore(hdfdata['dataset']['rf3'])
		
		# Save to master databank
		self.sweep_data[sweep_filename] = hdfdata
		
		if self.main_window is not None:
			self.main_window.status_bar.setLoadingFile(False)
		
		self.log.lowdebug(f"Finished reading file '{sweep_filename}'.")
		
		self.data_mtx.release()
	
	def import_sparam_file(self, sp_filename:str):
		''' Imports S-parameter data into the DLM's sparam dict'''
		
		self.log.lowdebug(f"Reading file from disk: {sp_filename}")
		
		try:
			if sp_filename[-4:].lower() == '.csv':
				sparam_data = read_rohde_schwarz_csv(sp_filename)
			else:
				
				# Read S-parameters
				sparam_data = read_s2p(sp_filename)
				
		except Exception as e:
			self.log.error(f"Failed to read S-parameter CSV file. {e}")
			sys.exit()
		
		if sparam_data is None:
			self.log.error(f"Failed to read S-parameter CSV file '{sp_filename}'.")
			return
		
		nd = {}
		
		try:
			nd['S11'] = sparam_data.S11_real + complex(0, 1)*sparam_data.S11_imag
		except:
			nd["S11"] = []
			
		try:
			nd['S21'] = sparam_data.S21_real + complex(0, 1)*sparam_data.S21_imag
		except:
			nd['S21'] = []
			
		try:
			nd['S12'] = sparam_data.S12_real + complex(0, 1)*sparam_data.S12_imag
		except:
			nd['S12'] = []
			
		try:
			nd['S22'] = sparam_data.S22_real + complex(0, 1)*sparam_data.S22_imag
		except:
			nd['S22'] = []
		
		nd['S11_dB'] = lin_to_dB(np.abs(nd['S11']))
		nd['S21_dB'] = lin_to_dB(np.abs(nd['S21']))
		nd['S12_dB'] = lin_to_dB(np.abs(nd['S12']))
		nd['S22_dB'] = lin_to_dB(np.abs(nd['S22']))
		
		try:
			nd['freq_GHz'] = sparam_data.freq_Hz/1e9
		except Exception as e:
			self.log.error(f"S-parameter data is corrupted. Missing frequency data.", detail=f"{e}. data_struct={sparam_data}")

		# Add dictionary to main databank
		self.sparam_data[sp_filename] = nd
		
		self.log.lowdebug(f"Finished reading file '{sp_filename}'.")
		
		self.data_mtx.release()

	def get_sweep(self, sweep_filename:str):
		''' Returns info struct for a sweep file.'''
		
		full_ds = self.get_sweep_full(sweep_filename)
		
		return full_ds['dataset']

class ImportSweepThread(QtCore.QThread):
		
	taskFinished = QtCore.pyqtSignal()
	
	def __init__(self, dlm:DataLoadingManager, sweep_filename:str):
		super().__init__()
		self.dlm = dlm
		self.sweep_filename = sweep_filename
	
	def run(self):
		print("  [[Sweep import thread running]]")
		self.dlm.import_sweep_file(self.sweep_filename)
		self.taskFinished.emit()

class ImportSparamThread(QtCore.QThread):
	
	taskFinished = QtCore.pyqtSignal()
	
	def __init__(self, dlm:DataLoadingManager, sweep_filename:str):
		super().__init__()
		self.dlm = dlm
		self.sweep_filename = sweep_filename
	
	def run(self):
		self.dlm.import_sparam_file(self.sweep_filename)
		self.taskFinished.emit()

class MasterData:
	''' Class to represent the data currently analyzed/plotted by the application'''
	
	def __init__(self, log:LogPile, dlm:DataLoadingManager):
		
		# Reinitialize all data as clear
		self.clear_sparam()
		self.clear_sweep()
	
		self.log = log
		self.dlm = dlm
		self.main_window = None
		
		# Mask of points to eliminate as outliers
		self.outlier_mask = []
		
		# datapath = get_datadir_path(rp=22, smc='B', sub_dirs=['*R4C4*C', 'Track 1 4mm'])
		datapath = get_datadir_path(rp=22, smc='B', sub_dirs=['*R4C4*C', 'Track 2 43mm'])
		# datapath = '/Volumes/M5 PERSONAL/data_transfer'
		if datapath is None:
			print(f"{Fore.RED}Failed to find data location{Style.RESET_ALL}")
			# datapath = "C:\\Users\\gmg3\\Documents\\GitHub\\ChillyInductor\\RP-22 Scripts\\SMC-B\\Measurement Scripts\\data"
			# print("WARNING WARNING REMOVE THIS")
			sys.exit()
		else:
			print(f"{Fore.GREEN}Located data directory at: {Fore.LIGHTBLACK_EX}{datapath}{Style.RESET_ALL}")

		# filename = "RP22B_MP3_t1_31July2024_R4C4T1_r1_autosave.hdf"
		# filename = "RP22B_MP3_t1_1Aug2024_R4C4T1_r1.hdf"
		# filename = "RP22B_MP3_t2_8Aug2024_R4C4T1_r1.hdf"
		# filename = "RP22B_MP3a_t3_19Aug2024_R4C4T2_r1.hdf"
		filename = "RP22B_MP3a_t2_20Aug2024_R4C4T2_r1.hdf"
		# filename = "RP22B_MP3a_t4_26Aug2024_R4C4T2_r1.hdf"
		
		analysis_file = os.path.join(datapath, filename)
		
		self.load_sweep(analysis_file)
		
		sp_datapath = get_datadir_path(rp=22, smc='B', sub_dirs=['*R4C4*C', 'Track 2 43mm', "Uncalibrated SParam", "Prf -30 dBm"])
		if sp_datapath is None:
			print(f"{Fore.RED}Failed to find s-parameter data location{Style.RESET_ALL}")
			sp_datapath = "M:\\data_transfer\\R4C4T2_Uncal_SParam\\Prf -30 dBm"
			# sys.exit()
		else:
			print(f"{Fore.GREEN}Located s-parameter data directory at: {Fore.LIGHTBLACK_EX}{sp_datapath}{Style.RESET_ALL}")
		
		# sp_filename = "Sparam_31July2024_-30dBm_R4C4T1_Wide.csv"
		sp_filename = "26Aug2024_Ch1ToCryoR_Ch2ToCryoL.csv"
		
		sp_analysis_file = os.path.join(sp_datapath, sp_filename)#"Sparam_31July2024_-30dBm_R4C4T1.csv")
		
		
		self.load_sparam(sp_analysis_file)

	def add_main_window(self, main_window):
		
		self.main_window = main_window
		self.dlm.main_window = main_window

	def clear_sparam(self):
		
		# Names of files loaded
		self.current_sparam_file = ""
		
		# S-Parameter arrays
		self.S_freq_GHz = []
		self.S11 = []
		self.S21 = []
		self.S12 = []
		self.S22 = []
		self.S11_dB = []
		self.S21_dB = []
		self.S12_dB = []
		self.S22_dB = []
		
		self._valid_sparam = False
	
	def clear_sweep(self):
		
		# Names of files loaded
		self.current_sweep_file = ""
		
		# Main sweep data - from file
		self.power_rf_dBm = []
		self.waveform_f_Hz = []
		self.waveform_s_dBm = []
		self.waveform_rbw_Hz = []
		self.MFLI_V_offset_V = []
		self.requested_Idc_mA = []
		self.raw_meas_Vdc_V = []
		self.Idc_mA = []
		self.detect_normal = []
		self.temperature_K = []
		
		# Main sweep data - derived
		self.rf1 = []
		self.rf2 = []
		self.rf3 = []
		self.rf1W = []
		self.rf2W = []
		self.rf3W = []
		self.unique_bias = []
		self.unique_pwr = []
		self.unique_freqs = []
		
		self._valid_sweep = False
	
	def load_sparam(self, sp_filename:str):
		''' Loads S-parameter data from the DLM.'''
		
		self.log.debug(f"MasterData loading s-parameter file: {sp_filename}")
		
		# Get data from manager
		spdict = self.dlm.get_sparam(sp_filename)
		
		if spdict is None:
			return
		
		if self.main_window is not None:
			self.main_window.status_bar.setLoadingRAM(True)
			self.main_window.app.processEvents()
		
		# Populate local variables
		self.S11 = spdict['S11']
		self.S21 = spdict['S21']
		self.S12 = spdict['S12']
		self.S22 = spdict['S22']
		self.S11_dB = spdict['S11_dB']
		self.S21_dB = spdict['S21_dB']
		self.S12_dB = spdict['S12_dB']
		self.S22_dB = spdict['S22_dB']
		self.S_freq_GHz = spdict['freq_GHz']
		
		self.current_sparam_file = sp_filename
		
		if len(self.S11) == 0 or len(self.S_freq_GHz) == 0:
			self._valid_sparam = False
		
		self._valid_sparam = True
		
		if self.main_window is not None:
			self.main_window.status_bar.setLoadingRAM(False)
			
		# all_lists = [self.S11, self.S21, self.S12, self.S22, self.S11_dB, self.S21_dB, , self.S12_dB, self.S22_dB, self.S_freq_GHz]
	
		# it = iter(all_lists)
		# the_len = len(next(it))
		# if not all(len(l) == the_len for l in it):
		# 	self._valid_sparam = False
	
	def load_sweep(self, sweep_filename:str):
		''' Loads sweep data from the DLM.'''
		
		# Get data from manager
		swdict = self.dlm.get_sweep(sweep_filename)
		
		if swdict is None:
			return
		
		if self.main_window is not None:
			self.main_window.status_bar.setLoadingRAM(True)
			self.main_window.app.processEvents()
		
		# populate local variables
		self.freq_rf_GHz = swdict['freq_rf_GHz']
		self.power_rf_dBm = swdict['power_rf_dBm']
		self.waveform_f_Hz = swdict['waveform_f_Hz']
		self.waveform_s_dBm = swdict['waveform_s_dBm']
		self.waveform_rbw_Hz = swdict['waveform_rbw_Hz']
		self.MFLI_V_offset_V = swdict['MFLI_V_offset_V']
		self.requested_Idc_mA = swdict['requested_Idc_mA']
		self.raw_meas_Vdc_V = swdict['raw_meas_Vdc_V']
		self.Idc_mA = swdict['Idc_mA']
		self.detect_normal = swdict['detect_normal']
		self.temperature_K = swdict['temperature_K']
		self.rf1 = swdict['rf1']
		self.rf2 = swdict['rf2']
		self.rf3 = swdict['rf3']
		self.rf1W = swdict['rf1W']
		self.rf2W = swdict['rf2W']
		self.rf3W = swdict['rf3W']
		self.total_power = swdict['total_power']
		self.ce2 = swdict['ce2']
		self.ce3 = swdict['ce3']
		self.unique_bias = swdict['unique_bias']
		self.unique_pwr = swdict['unique_pwr']
		self.unique_freqs = swdict['unique_freqs']
		self.extra_z = swdict['extra_z']
		self.zs_extra_z = swdict['zs_extra_z']
		self.zs_meas_Idc = swdict['zs_meas_Idc']
		self.zs_ce2 = swdict['zs_ce2']
		self.zs_ce3 = swdict['zs_ce3']
		self.zs_rf1 = swdict['zs_rf1']
		self.zs_rf2 = swdict['zs_rf2']
		self.zs_rf3 = swdict['zs_rf3']
		
		self.outlier_mask = (self.power_rf_dBm == self.power_rf_dBm)
		
		self.current_sweep_file = sweep_filename
		
		if len(self.power_rf_dBm) == 0:
			self._valid_sweep = False
			return
		
		all_lists = [self.freq_rf_GHz, self.power_rf_dBm, self.waveform_f_Hz, self.waveform_s_dBm, self.waveform_rbw_Hz, self.MFLI_V_offset_V, self.requested_Idc_mA, self.raw_meas_Vdc_V, self.Idc_mA, self.detect_normal, self.temperature_K, self.rf1, self.rf2, self.rf3, self.rf1W, self.rf2W, self.rf3W, self.total_power, self.ce2, self.ce3, self.unique_bias, self.unique_freqs, self.unique_pwr, self.extra_z, self.zs_extra_z, self.zs_meas_Idc, self.zs_ce2, self.zs_ce3, self.zs_rf1, self.zs_rf2, self.zs_rf3]
	
		it = iter(all_lists)
		the_len = len(next(it))
		if not all(len(l) == the_len for l in it):
			self._valid_sweep = False
		
		self._valid_sweep = True
		
		if self.main_window is not None:
			self.main_window.status_bar.setLoadingRAM(False)
		
		
	def rebuild_outlier_mask(self, ce2_zscore:float, ce3_zscore:float, extraz_zscore:float, extraz_val:float, rf1_val:float):
		
		# Process CE2
		if ce2_zscore is not None:
			self.outlier_mask = (self.zs_ce2 < ce2_zscore)
		else:
			self.outlier_mask = (self.zs_ce2 == self.zs_ce2)
		
		# Process CE3
		if ce3_zscore is not None:
			self.outlier_mask = self.outlier_mask & (self.zs_ce3 < ce3_zscore)

		# Process extra-z (Zscore)
		if extraz_zscore is not None:
			self.outlier_mask = self.outlier_mask & (self.zs_extra_z < extraz_zscore)
		
		# Process extra-z (value)
		if extraz_val is not None:
			self.outlier_mask = self.outlier_mask & (self.extra_z < extraz_val)
		
		# Process rf1 (value)
		if rf1_val is not None:
			self.outlier_mask = self.outlier_mask & (self.rf1 > rf1_val)
		
	def is_valid_sweep(self):
		return self._valid_sweep
	
	def is_valid_sparam(self):
		return self._valid_sparam
		
##--------------------------------------------
# Create GUI

def get_graph_lims(data:list, step=None):
	
	umin = np.min(data)
	umax = np.max(data)
	
	return [np.floor(umin/step)*step, np.ceil(umax/step)*step]

def calc_zscore(data:list):
	data = np.array(data)
	mu = np.mean(data)
	stdev = np.std(data)
	return (data - mu)/stdev
	

GCOND_REMOVE_OUTLIERS = 'remove_outliers'
GCOND_OUTLIER_ZSCE2 = 'remove_outliers_ce2_zscore'
GCOND_OUTLIER_ZSCE3 = 'remove_outliers_ce3_zscore'
GCOND_OUTLIER_ZSEXTRAZ = 'remove_outliers_extraz_zscore'
GCOND_OUTLIER_VALEXTRAZ = 'remove_outliers_extraz_val'
GCOND_OUTLIER_VALRF1 = 'remove_outliers_rf1_val'
GCOND_FREQXAXIS_ISFUND = 'freqxaxis_isfund'
GCOND_BIASXAXIS_ISMEAS = 'biasxaxis_ismeas'
GCOND_ADJUST_SLIDER = 'adjust_sliders'

class StatusBar(QStatusBar):

	def __init__(self):
		super().__init__()
		
		self.loadfile_label = QLabel("Disk (Sweep):")
		self.addPermanentWidget(self.loadfile_label)
		
		# Set layout
		self.loadfile_pb = QProgressBar(self)
		self.loadfile_pb.setRange(0,1)
		self.loadfile_pb.setFixedWidth(100)
		self.addPermanentWidget(self.loadfile_pb)
		
		self.loadspfile_label = QLabel("Disk (SParam):")
		self.addPermanentWidget(self.loadspfile_label)
		
		# Set layout
		self.loadspfile_pb = QProgressBar(self)
		self.loadspfile_pb.setRange(0,1)
		self.loadspfile_pb.setFixedWidth(100)
		self.addPermanentWidget(self.loadspfile_pb)
		
		self.ram_label = QLabel("Loading Dataset:")
		self.addPermanentWidget(self.ram_label)
		
		# Set layout
		self.ram_pb = QProgressBar(self)
		self.ram_pb.setRange(0,1)
		self.ram_pb.setFixedWidth(100)
		self.addPermanentWidget(self.ram_pb)
		
		self.render_label = QLabel("Rendering:")
		self.addPermanentWidget(self.render_label)
		
		# Set layout
		self.render_pb = QProgressBar(self)
		self.render_pb.setRange(0,1)
		self.render_pb.setFixedWidth(100)
		self.addPermanentWidget(self.render_pb)
		
		
		
		
		
		
		
		# # Make frame
		# self.frame = QGroupBox()
		# self.frame.setLayout(self.grid)
		# self.overgrid = QGridLayout()
		# self.overgrid.addWidget(self.frame, 0, 0)
		# self.setLayout(self.overgrid)

		# self.myLongTask = TaskThread()
		# self.myLongTask.taskFinished.connect(self.end_loadfile)
		
	def setLoadingFile(self, status:bool):
		if status:
			self.loadfile_pb.setRange(0,0)
		else:
			self.loadfile_pb.setRange(0,1)
	
	def setLoadingSPFile(self, status:bool):
		if status:
			self.loadspfile_pb.setRange(0,0)
		else:
			self.loadspfile_pb.setRange(0,1)
	
	def setLoadingRAM(self, status:bool):
		if status:
			self.ram_pb.setRange(0,0)
		else:
			self.ram_pb.setRange(0,1)
	
	def setRendering(self, status:bool):
		if status:
			self.render_pb.setRange(0,0)
		else:
			self.render_pb.setRange(0,1)
	
			


# class TaskThread(QtCore.QThread):
# 	taskFinished = QtCore.pyqtSignal()
# 	def run(self):
# 		time.sleep(3)
# 		self.taskFinished.emit() 

class DataCompareWindow(QMainWindow):
	
	def __init__(self, files:list, log:LogPile, dlm:DataLoadingManager):
		super().__init__()
		
		self.setWindowTitle("Data Sweep Comparison")
		
		self.files = files
		self.dlm = dlm
		self.log = log
		
		# Create figure
		self.fig1, ax_list = plt.subplots(3, 1)
		self.ax1 = ax_list[0]
		self.ax2 = ax_list[1]
		self.ax3 = ax_list[2]
		
		# Create widgets
		self.fig1cvs = FigureCanvas(self.fig1)
		self.toolbar1 = NavigationToolbar2QT(self.fig1cvs, self)
		
		self.render_plot()
		
		# Add widgets to parent-widget and set layout
		self.grid = QtWidgets.QGridLayout()
		self.grid.addWidget(self.toolbar1, 0, 0)
		self.grid.addWidget(self.fig1cvs, 1, 0)
		
		central_widget = QtWidgets.QWidget()
		central_widget.setLayout(self.grid)
		self.setCentralWidget(central_widget)
	
	def render_plot(self):
		
		self.ax1.cla()
		self.ax2.cla()
		self.ax3.cla()
		
		markers = []
		marker_sizes = []
		colors = []
		labels = []
		
		# Get conf dict for each file
		conf_list = []
		for fn in self.files:
			bfn = os.path.basename(fn) # Strip file name from full path
			
			# Access data from DLM
			full_data = self.dlm.get_sweep_full(fn)
			
			try:
				conf_str = full_data['info']['configuration']
				if type(conf_str) != str:
					print(type(conf_str))
					conf_str = conf_str.decode()
				conf_list.append(json.loads(conf_str))
			except Exception as e:
				self.log.warning(f"Failed to load configuration data for file: {bfn}.", detail=f"{e}")
				continue
			
			markers.append('s')
			marker_sizes.append(10)
			colors.append((0, 0, 0.7))
			labels.append(bfn)
		
		axs = [self.ax1, self.ax2, self.ax3]
		
		# Scan over files
		for src_idx, conf in enumerate(conf_list):
			
			# Scan over parameters
			data_idx = 0
			for k in conf.keys():
				
				# Skip lists
				if type(conf[k]) == list:continue
				
				# Get values
				try:
					vals = interpret_range(conf[k])
				except Exception as e:
					self.log.debug(f"Interpret range failed. Skipping parameter '{k}' in comparison.", detail=f"{e}")
					continue
				
				unit_str = conf[k]['unit']
				
				# Plot data
				axs[data_idx].grid(True)
				axs[data_idx].scatter(vals, [len(conf_list)-src_idx]*len(vals), [marker_sizes[src_idx]]*len(vals), marker=markers[src_idx], color=colors[src_idx], label=labels[src_idx])
				axs[data_idx].set_xlabel(f"{k} [{unit_str}]")
				
				# Set parameters on last loops
				if src_idx == len(conf_list) -1:
					# axs[data_idx].legend()
					axs[data_idx].set_yticks(list(range(1, len(conf_list)+1)))
					axs[data_idx].set_yticklabels(reversed(labels))
				
				data_idx += 1

		self.fig1.tight_layout()
		
		# for (x, y, leglab) in zip(self.x_data, self.y_zscore, self.legend_labels):
		# 	self.ax1.plot(x, y, label=leglab, linestyle=':', marker='X')
			
		# self.ax1.set_ylabel("Z-Score")
		# self.ax1.legend()
		# self.ax1.grid(True)
		# self.ax1.set_xlabel(self.x_label)
		
		# if type(self.y_zscore[0]) == list or type(self.y_zscore[0]) == np.ndarray: # 2D list
			
		# 	for (x, y, leglab) in zip(self.x_data, self.y_zscore, self.legend_labels):
		# 		self.ax1.plot(x, y, label=leglab)
			
		# 	self.ax1.set_ylabel("Z-Score")
		# 	self.ax1.legend()
		# 	self.ax1.grid(True)
		# 	self.ax1.set_xlabel(self.x_label)
		# else:
		# 	self.ax1.plot(self.x_data, self.y_zscore)
		# 	self.ax1.set_xlabel(self.x_label)
		# 	self.ax1.set_ylabel(self.legend_labels)
		# 	self.ax1.grid(True)
		
		self.fig1.canvas.draw_idle()
		
		

class DataSelectWidget(QWidget):
	
	def __init__(self, global_conditions:dict, log:LogPile, mdata:MasterData, replot_handle, dataset_changed_handle, show_frame:bool=False):
		super().__init__()
		self.mdata = mdata
		self.log = log
		self.gcond = global_conditions
		self.replot_handle = replot_handle
		self.dataset_changed_handle = dataset_changed_handle
		
		##------------ Make filter box ---------------
		
		self.filt_box = QGroupBox()
		self.filt_box.setStyleSheet("QGroupBox{border:0;}")
		self.filt_box.setFixedWidth(170)
		
		self.en_wild_filt_cb = QCheckBox("Enable Filter")
		self.en_wild_filt_cb.setChecked(True)
		self.en_wild_filt_cb.stateChanged.connect(self.reinit_file_list)
		
		self.filt_label1 = QLabel("Filter text:")
		
		self.wild_filt_edit = QLineEdit()
		try:
			self.wild_filt_edit.setText(self.mdata.dlm.data_conf["wild_filt_default"])
		except:
			self.wild_filt_edit.setText("")
		self.wild_filt_edit.editingFinished.connect(self.reinit_file_list)
		self.wild_filt_edit.setFixedWidth(150)
		
		self.filt_label2 = QLabel("(* = wildcard)")
		
		self.filt_boxgrid = QGridLayout()
		self.filt_boxgrid.addWidget(self.en_wild_filt_cb, 0, 0)
		self.filt_boxgrid.addWidget(self.filt_label1, 1, 0)
		self.filt_boxgrid.addWidget(self.wild_filt_edit, 2, 0)
		self.filt_boxgrid.addWidget(self.filt_label2, 3, 0)
		self.filt_box.setLayout(self.filt_boxgrid)
		
		##------------ End filter box ---------------
		
		self.chip_select_label = QLabel("Chip:")
		
		self.chip_select = QListWidget()
		self.chip_select.setFixedSize(QSize(75, 100))
		self.chip_select.itemClicked.connect(self.reinit_track_list)
		
		self.track_select_label = QLabel("Track:")
		
		self.track_select = QListWidget()
		self.track_select.setFixedSize(QSize(120, 100))
		self.track_select.itemClicked.connect(self.reinit_file_list)
		
		self.sweep_select_label = QLabel("Sweep:")
		
		self.dset_select = QListWidget()
		self.dset_select.setFixedSize(QSize(350, 100))
		self.dset_select.itemClicked.connect(self.reload_sweep)
		
		self.sparam_select_label = QLabel("S-Parameters:")
		
		self.sparam_select = QListWidget()
		self.sparam_select.setFixedSize(QSize(350, 100))
		self.sparam_select.itemClicked.connect(self.reload_sparam)
		
		if cli_args.theme:
			self.compare_btn = QPushButton("Compare\nDatasets", icon=QIcon("./assets/compare_src_dr.png"))
		else:
			self.compare_btn = QPushButton("Compare\nDatasets", icon=QIcon("./assets/compare_src.png"))
			
		self.compare_btn.setFixedSize(130, 40)
		self.compare_btn.clicked.connect(self._compare_datasets)
		self.compare_btn.setIconSize(QSize(48, 32))
		
		self.arrow_label = QLabel()
		if cli_args.theme:
			self.arrow_label.setPixmap(QPixmap("./assets/right_arrow_dr.png").scaledToWidth(40))
		else:
			self.arrow_label.setPixmap(QPixmap("./assets/right_arrow.png").scaledToWidth(40))
		
		self.loadset_btn = QPushButton("Load\nSelected", icon=QIcon("./assets/reload_data.png"))
		self.loadset_btn.setFixedSize(120, 40)
		# self.loadset_btn.clicked.connect(self._load_selected)
		self.loadset_btn.setIconSize(QSize(48, 32))
		
		if cli_args.theme:
			self.loadconf_btn = QPushButton("Load Config\nFile", icon=QIcon("./assets/pick_conf_dr.png"))
		else:
			self.loadconf_btn = QPushButton("Load Config\nFile", icon=QIcon("./assets/pick_conf.png"))
		self.loadconf_btn.setFixedSize(130, 40)
		self.loadconf_btn.clicked.connect(self._load_conf_file)
		self.loadconf_btn.setIconSize(QSize(48, 32))
		
		self.bottom_spacer = QSpacerItem(10, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
		self.right_spacer = QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
		
		self.grid = QGridLayout()
		
		self.grid.addWidget(self.filt_box, 0, 0, 3, 1)
		
		self.grid.addWidget(self.compare_btn, 1, 1)
		self.grid.addWidget(self.loadconf_btn, 2, 1)
		
		self.grid.addWidget(self.chip_select_label, 0, 2)
		self.grid.addWidget(self.chip_select, 1, 2, 2, 1)
		self.grid.addWidget(self.track_select_label, 0, 3)
		self.grid.addWidget(self.track_select, 1, 3, 2, 1)
		
		self.grid.addWidget(self.arrow_label, 1, 4, alignment=QtCore.Qt.AlignmentFlag.AlignBottom)
		
		self.grid.addWidget(self.sweep_select_label, 0, 5)
		self.grid.addWidget(self.dset_select, 1, 5, 2, 1)
		self.grid.addWidget(self.sparam_select_label, 0, 6)
		self.grid.addWidget(self.sparam_select, 1, 6, 2, 1)
		
		self.grid.addWidget(self.loadset_btn, 1, 7)
		self.grid.addItem(self.bottom_spacer, 3, 0, 1, 9)
		self.grid.addItem(self.right_spacer, 0, 8, 3, 1)
		
		if show_frame:
			self.frame = QGroupBox("Data Selector")
			self.frame.setLayout(self.grid)
			self.overgrid = QGridLayout()
			self.overgrid.addWidget(self.frame, 0, 0)
			self.setLayout(self.overgrid)
		else:
			self.setLayout(self.grid)
		
		self.reinit_chip_list()
	
	def _compare_datasets(self):
		
		# Get selected chip and track
		chip_item = self.chip_select.currentItem()
		if chip_item is None:
			return
		track_item = self.track_select.currentItem()
		if track_item is None:
			return
		
		# Find matching full path
		full_path = None
		for ds in self.mdata.dlm.data_conf['sweep_sources']:
			
			# Skip wrong chips
			if ds['chip_name'] != chip_item.text():
				continue
			
			# Skip wrong tracks
			if ds['track'] != track_item.text():
				continue
			
			full_path = ds['full_path']
		
		# Abort if no path appears
		if full_path is None:
			self.log.error(f"Path to data directory not found!")
			return
		
		# Make list of file names
		file_list = [os.path.join(full_path, self.dset_select.item(x).text()) for x in range(self.dset_select.count())]
		
		# Create window
		self.dcw = DataCompareWindow(file_list, self.log, self.mdata.dlm)
		self.dcw.show()
	
	def _load_conf_file(self):
		
		openfile, __ = QFileDialog.getOpenFileName()
		self.mdata.dlm.load_conf(openfile)
		
		self.reinit_chip_list()
		
	def reinit_chip_list(self):
		
		self.chip_select.clear()
		
		# Get list of chips
		chips = []
		for ds in self.mdata.dlm.data_conf['sweep_sources']:
			if ds['chip_name'] not in chips:
				chips.append(ds['chip_name'])
				
				# Update widget
				self.chip_select.addItem(ds['chip_name'])
		
		self.chip_select.setCurrentRow(0)
		
		# If chips exist, pick on and reinit track list
		if len(chips) > 0:
			self.chip_select.setCurrentRow(0)
			self.reinit_track_list()
	
	def reinit_track_list(self):
		
		# Clear tracks
		self.track_select.clear()
		
		# Get selected chip
		item = self.chip_select.currentItem()
		if item is None:
			return
		
		item_name = item.text()
		
		# Repopulate tracks
		tracks = []
		for ds in self.mdata.dlm.data_conf['sweep_sources']:
			
			# Skip wrong chips
			if ds['chip_name'] != item_name:
				continue
			
			if ds['track'] not in tracks:
				tracks.append(ds['track'])
				self.track_select.addItem(ds['track'])
		
		# If tracks exist, reinit file list
		if len(tracks) > 0:
			self.track_select.setCurrentRow(0)
			self.reinit_file_list()
	
	def reinit_file_list(self):
		
		# Clear file list
		self.dset_select.clear()
		self.sparam_select.clear()
		
		# Get selected chip and track
		chip_item = self.chip_select.currentItem()
		if chip_item is None:
			return
		track_item = self.track_select.currentItem()
		if track_item is None:
			return
		
		#------ Populate Sweep list --------
		
		# Find matching full path
		full_path = None
		for ds in self.mdata.dlm.data_conf['sweep_sources']:
			
			# Skip wrong chips
			if ds['chip_name'] != chip_item.text():
				continue
			
			# Skip wrong tracks
			if ds['track'] != track_item.text():
				continue
			
			full_path = ds['full_path']
		
		# Abort if no path appears
		if full_path is None:
			self.log.error(f"Path to data directory not found!")
			return
		
		# Get list of files in directory
		file_list = [f for f in os.listdir(full_path) if os.path.isfile(os.path.join(full_path, f))]
		self.log.debug(f"Full path = {full_path}, listdir={os.listdir(full_path)}")
		
		# Scan over directory, add all matching files
		has_items = False
		for fn in file_list:
			
			# Skip files with no extension, or double extensions
			if fn.count('.') != 1:
				continue
			
			# Skip files with names too short
			if len(fn) < 5:
				continue
			
			# Check extension
			if fn[-4:].lower() != ".hdf":
				continue
			
			# Handle wildcard match filtering
			if self.en_wild_filt_cb.isChecked():
				
				# Skip file if doesn't match
				if wildcard([fn], self.wild_filt_edit.text()) is None:
					continue
			
			has_items = True
			self.dset_select.addItem(fn)
		
		# If dsets exist, pick first
		if has_items:
			self.dset_select.setCurrentRow(0)
			self.reload_sweep()
		
		#------ SParam Sweep list --------
		
		# Find relevant S-parameter sources
		has_items = False
		for sps in self.mdata.dlm.data_conf['sparam_sources']:
			
			# Skip wrong chips
			if sps['chip_name'] != chip_item.text():
				continue
			
			# Skip wrong tracks
			if sps['track'] != track_item.text():
				continue
			
			# Skip sets with invalid data
			if sps['cryo_full_path'] is None:
				continue
			
			# Add to list
			self.sparam_select.addItem(sps['sparam_set_name'])
			has_items = True
		
		# If dsets exist, pick first
		if has_items:
			self.sparam_select.setCurrentRow(0)
			self.reload_sparam()
	
	def reload_sparam(self):
		
		self.log.lowdebug(f"Reloading s-parameter data")
		
		# Get selected file
		item = self.sparam_select.currentItem()
		if item is None:
			return
		file_name = item.text()
		
		self.log.lowdebug(f"Selected S-parameter file: {file_name}")
		
		# Find full path for file
		full_path = None
		for sps in self.mdata.dlm.data_conf['sparam_sources']:
			
			if sps['sparam_set_name'] == file_name:
				full_path = sps['cryo_full_path']
				break
		
		if full_path is None:
			self.log.error(f"Cannot reload sparameters - file not found.")
			return
		
		# Realod data
		self.mdata.load_sparam(full_path)
		
		# Replot graphs
		self.replot_handle()
		
	def reload_sweep(self):
		
		self.log.lowdebug(f"Reloading sweep data")
		
		# Get selected chip and track
		chip_item = self.chip_select.currentItem()
		if chip_item is None:
			return
		track_item = self.track_select.currentItem()
		if track_item is None:
			return
		
		# Get selected file
		item = self.dset_select.currentItem()
		if item is None:
			return
		file_name = item.text()
		
		self.log.lowdebug(f"Selected sweep file: {file_name}")
		
		# Find full path for file
		full_path = None
		for ds in self.mdata.dlm.data_conf['sweep_sources']:
			
			# Skip wrong chips
			if ds['chip_name'] != chip_item.text():
				continue
			
			# Skip wrong tracks
			if ds['track'] != track_item.text():
				continue
			
			full_path = ds['full_path']
		
		if full_path is None:
			self.log.error(f"Cannot reload sweep data - path not found.")
			return
		
		fullfile = os.path.join(full_path, file_name)
		
		# Realod data
		self.mdata.load_sweep(fullfile)
		
		# Update slider values
		self.dataset_changed_handle()
		
		# Replot graphs
		self.replot_handle()
	
	def reanalyze(self):
		
		self.log.lowdebug(f"Reanalyzing DataSelectWidget's control settings.")

class OutlierControlWidget(QWidget):
	
	def __init__(self, global_conditions:dict, log:LogPile, mdata:MasterData, replot_handle, reinit_handle, show_frame:bool=False):
		super().__init__()
		
		self.gcond = global_conditions
		self.log = log
		self.mdata = mdata
		self.replot_handle = replot_handle
		self.reinit_handle = reinit_handle
		
		self.enable_cb = QCheckBox("Remove Outliers")
		self.enable_cb.setChecked(True)
		self.enable_cb.stateChanged.connect(self.reanalyze)
		

			#-------- CE 2 subgroup (Zscore)
			
		self.ce2_gbox = QGroupBox("CE2")
		
		self.zscore_ce2_cb = QCheckBox("En")
		self.zscore_ce2_cb.stateChanged.connect(self.reanalyze)
		
		self.zscore_ce2_label = QLabel("Z-Score < ")
		self.zscore_ce2_edit = QLineEdit()
		self.zscore_ce2_edit.setValidator(QDoubleValidator())
		self.zscore_ce2_edit.setText("10")
		self.zscore_ce2_edit.setFixedWidth(40)
		self.zscore_ce2_edit.editingFinished.connect(self.reanalyze)
		
		self.ce2_gboxgrid = QGridLayout()
		self.ce2_gboxgrid.addWidget(self.zscore_ce2_label, 0, 0)
		self.ce2_gboxgrid.addWidget(self.zscore_ce2_edit, 0, 1)
		self.ce2_gboxgrid.addWidget(self.zscore_ce2_cb, 0, 2)
		self.ce2_gbox.setLayout(self.ce2_gboxgrid)
		
			#-------- CE 3 subgroup (Zscore)
			
		self.ce3_gbox = QGroupBox("CE3")
		
		self.zscore_ce3_cb = QCheckBox("En")
		self.zscore_ce3_cb.stateChanged.connect(self.reanalyze)
		
		self.zscore_ce3_label = QLabel("Z-Score < ")
		self.zscore_ce3_edit = QLineEdit()
		self.zscore_ce3_edit.setValidator(QDoubleValidator())
		self.zscore_ce3_edit.setText("10")
		self.zscore_ce3_edit.setFixedWidth(40)
		self.zscore_ce3_edit.editingFinished.connect(self.reanalyze)
		
		self.ce3_gboxgrid = QGridLayout()
		self.ce3_gboxgrid.addWidget(self.zscore_ce3_label, 0, 0)
		self.ce3_gboxgrid.addWidget(self.zscore_ce3_edit, 0, 1)
		self.ce3_gboxgrid.addWidget(self.zscore_ce3_cb, 0, 2)
		self.ce3_gbox.setLayout(self.ce3_gboxgrid)
			
			#------------- Extra Z subgroup (Zscore)
		
		self.extraz_gbox = QGroupBox("Extra Impedance")
		
		self.zscore_extraz_cb = QCheckBox("En")
		self.zscore_extraz_cb.stateChanged.connect(self.reanalyze)
		
		self.zscore_extraz_label = QLabel("Z-Score < ")
		self.zscore_extraz_edit = QLineEdit()
		self.zscore_extraz_edit.setValidator(QDoubleValidator())
		self.zscore_extraz_edit.setText("2")
		self.zscore_extraz_edit.setFixedWidth(40)
		self.zscore_extraz_edit.editingFinished.connect(self.reanalyze)
		
		self.val_extraz_cb = QCheckBox("En")
		self.val_extraz_cb.stateChanged.connect(self.reanalyze)
		
		self.val_extraz_label = QLabel("Value (Ω) < ")
		self.val_extraz_edit = QLineEdit()
		self.val_extraz_edit.setValidator(QDoubleValidator())
		self.val_extraz_edit.setText("20")
		self.val_extraz_edit.setFixedWidth(40)
		self.val_extraz_edit.editingFinished.connect(self.reanalyze)
		
		# self.extraz_gboxgrid = QGridLayout()
		# self.extraz_gboxgrid.addWidget(self.zscore_extraz_cb, 0, 0, 1, 2)
		# self.extraz_gboxgrid.addWidget(self.zscore_extraz_label, 1, 0)
		# self.extraz_gboxgrid.addWidget(self.zscore_extraz_edit, 1, 1)
		# self.extraz_gbox.setLayout(self.extraz_gboxgrid)
		
		self.extraz_gboxgrid = QGridLayout()
		self.extraz_gboxgrid.addWidget(self.val_extraz_label, 0, 0)
		self.extraz_gboxgrid.addWidget(self.val_extraz_edit, 0, 1)
		self.extraz_gboxgrid.addWidget(self.val_extraz_cb, 0, 2)
		
		self.extraz_gboxgrid.addWidget(self.zscore_extraz_label, 1, 0)
		self.extraz_gboxgrid.addWidget(self.zscore_extraz_edit, 1, 1)
		self.extraz_gboxgrid.addWidget(self.zscore_extraz_cb, 1, 2)
		
		self.extraz_gbox.setLayout(self.extraz_gboxgrid)
		
			#------------- Extra Z subgroup
		
		self.rf1_gbox = QGroupBox("Harmonic Power")
		
		self.val_rf1_cb = QCheckBox("En")
		self.val_rf1_cb.stateChanged.connect(self.reanalyze)
		
		self.val_rf1_label = QLabel("Fund (dBm) > ")
		self.val_rf1_edit = QLineEdit()
		self.val_rf1_edit.setValidator(QDoubleValidator())
		self.val_rf1_edit.setText("-40")
		self.val_rf1_edit.setFixedWidth(40)
		self.val_rf1_edit.editingFinished.connect(self.reanalyze)
		
		self.rf1_gboxgrid = QGridLayout()
		self.rf1_gboxgrid.addWidget(self.val_rf1_label, 0, 0)
		self.rf1_gboxgrid.addWidget(self.val_rf1_edit, 0, 1)
		self.rf1_gboxgrid.addWidget(self.val_rf1_cb, 0, 2)
		self.rf1_gbox.setLayout(self.rf1_gboxgrid)
		
			#------------- End subgroups
		
		self.bottom_spacer = QSpacerItem(10, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
		
		self.grid = QGridLayout()
		self.grid.addWidget(self.enable_cb, 0, 0, 1, 2, alignment=QtCore.Qt.AlignmentFlag.AlignTop)
		self.grid.addWidget(self.ce2_gbox, 1, 0)
		self.grid.addWidget(self.ce3_gbox, 2, 0)
		self.grid.addWidget(self.extraz_gbox, 3, 0)
		self.grid.addWidget(self.rf1_gbox, 4, 0)
		# self.grid.addWidget(self.zscore_label, 1, 0, alignment=QtCore.Qt.AlignmentFlag.AlignTop)
		# self.grid.addWidget(self.zscore_edit, 1, 1, alignment=QtCore.Qt.AlignmentFlag.AlignTop)
		self.grid.addItem(self.bottom_spacer, 5, 0)
		
		if show_frame:
			self.frame = QGroupBox("Outlier Control")
			self.frame.setLayout(self.grid)
			self.overgrid = QGridLayout()
			self.overgrid.addWidget(self.frame, 0, 0)
			self.setLayout(self.overgrid)
		else:
			self.setLayout(self.grid)
		
		self.reanalyze()
		
	def reanalyze(self):
		
		self.log.lowdebug(f"Reanalyzing OutlierControlWidget's control settings.")
		
		# Update enable/disable all 
		self.gcond[GCOND_REMOVE_OUTLIERS] = self.enable_cb.isChecked()
		
		# Update CE2 spec (Zscore)
		try:
			if self.zscore_ce2_cb.isChecked():
				self.gcond[GCOND_OUTLIER_ZSCE2] = float(self.zscore_ce2_edit.text())
			else:
				self.gcond[GCOND_OUTLIER_ZSCE2] = None
		except Exception as e:
			self.log.warning("Failed to interpret CE2 Z-score value. Defaulting to 10.", detail=f"{e}")
			self.zscore_ce2_edit.setText("10")
			self.gcond[GCOND_OUTLIER_ZSCE2] = 10
			
		# Update CE3 spec (Zscore)
		try:
			if self.zscore_ce3_cb.isChecked():
				self.gcond[GCOND_OUTLIER_ZSCE3] = float(self.zscore_ce3_edit.text())
			else:
				self.gcond[GCOND_OUTLIER_ZSCE3] = None
		except Exception as e:
			self.log.warning("Failed to interpret CE3 Z-score value. Defaulting to 10.", detail=f"{e}")
			self.zscore_ce3_edit.setText("10")
			self.gcond[GCOND_OUTLIER_ZSCE3] = 10
			
		# Update extra z spec (Zscore)
		try:
			if self.zscore_extraz_cb.isChecked():
				self.gcond[GCOND_OUTLIER_ZSEXTRAZ] = float(self.zscore_extraz_edit.text())
			else:
				self.gcond[GCOND_OUTLIER_ZSEXTRAZ] = None
		except Exception as e:
			self.log.warning("Failed to interpret extra-Z Z-score value. Defaulting to 2.", detail=f"{e}")
			self.zscore_edit.setText("2")
			self.gcond[GCOND_OUTLIER_ZSEXTRAZ] = 2
		
		# Update extra z spec (value)
		try:
			if self.val_extraz_cb.isChecked():
				self.gcond[GCOND_OUTLIER_VALEXTRAZ] = float(self.val_extraz_edit.text())
			else:
				self.gcond[GCOND_OUTLIER_VALEXTRAZ] = None
		except Exception as e:
			self.log.warning("Failed to interpret extra-Z value for outlier removal. Defaulting to 20.", detail=f"{e}")
			self.zscore_edit.setText("20")
			self.gcond[GCOND_OUTLIER_VALEXTRAZ] = 20
		
		# Update extra z spec (value)
		try:
			if self.val_rf1_cb.isChecked():
				self.gcond[GCOND_OUTLIER_VALRF1] = float(self.val_rf1_edit.text())
			else:
				self.gcond[GCOND_OUTLIER_VALRF1] = None
		except Exception as e:
			self.log.warning("Failed to interpret RF1 value for outlier removal. Defaulting to -40 dBm.", detail=f"{e}")
			self.zscore_edit.setText("-40")
			self.gcond[GCOND_OUTLIER_VALRF1] = -40
		
		self.mdata.rebuild_outlier_mask(self.gcond[GCOND_OUTLIER_ZSCE2], self.gcond[GCOND_OUTLIER_ZSCE3], self.gcond[GCOND_OUTLIER_ZSEXTRAZ], self.gcond[GCOND_OUTLIER_VALEXTRAZ], self.gcond[GCOND_OUTLIER_VALRF1])
		
		# Reinitialize all auto-lims
		self.reinit_handle()
		
		# Replot all graph
		self.replot_handle()
		
class ZScorePlotWindow(QMainWindow):
	
	def __init__(self, x_data, y_zscore, legend_labels, x_label):
		super().__init__()
		
		self.x_data = x_data
		self.y_zscore = y_zscore
		self.legend_labels = legend_labels
		self.x_label = x_label
		
		# Create figure
		self.fig1, self.ax1 = plt.subplots(1, 1)
		
		# Create widgets
		self.fig1cvs = FigureCanvas(self.fig1)
		self.toolbar1 = NavigationToolbar2QT(self.fig1cvs, self)
		
		self.render_plot()
		
		# Add widgets to parent-widget and set layout
		self.grid = QtWidgets.QGridLayout()
		self.grid.addWidget(self.toolbar1, 0, 0)
		self.grid.addWidget(self.fig1cvs, 1, 0)
		
		central_widget = QtWidgets.QWidget()
		central_widget.setLayout(self.grid)
		self.setCentralWidget(central_widget)
	
	def render_plot(self):
		
		self.ax1.cla()
		
		for (x, y, leglab) in zip(self.x_data, self.y_zscore, self.legend_labels):
			self.ax1.plot(x, y, label=leglab, linestyle=':', marker='X')
			
		self.ax1.set_ylabel("Z-Score")
		self.ax1.legend()
		self.ax1.grid(True)
		self.ax1.set_xlabel(self.x_label)
		
		# if type(self.y_zscore[0]) == list or type(self.y_zscore[0]) == np.ndarray: # 2D list
			
		# 	for (x, y, leglab) in zip(self.x_data, self.y_zscore, self.legend_labels):
		# 		self.ax1.plot(x, y, label=leglab)
			
		# 	self.ax1.set_ylabel("Z-Score")
		# 	self.ax1.legend()
		# 	self.ax1.grid(True)
		# 	self.ax1.set_xlabel(self.x_label)
		# else:
		# 	self.ax1.plot(self.x_data, self.y_zscore)
		# 	self.ax1.set_xlabel(self.x_label)
		# 	self.ax1.set_ylabel(self.legend_labels)
		# 	self.ax1.grid(True)
		
		self.fig1.canvas.draw_idle()

class TabPlotWidget(QWidget):
	
	def __init__(self, global_conditions:dict, log:LogPile, mdata:MasterData):
		super().__init__()
		
		self.log = log
		self.mdata = mdata
		self.gcond = global_conditions
		self.conditions = {}
		
		self._is_active = False # Indicates if the current tab is displayed
		self.plot_is_current = False # Does the plot need to be re-rendered?
		
		self.zscore_data = []
		self.zscore_labels = []
		self.zscore_x_data = []
		self.zscore_x_label = ""
		
		self.fig_list = [] # List of figures to save when save graph is activated
		
	def init_zscore_data(self, y_data:list, legend_labels:list, x_data:list=[], x_label:str="Datapoint Index"):
		''' y_data, x_data are lists of lists. legend_label is a list of strings. Each list row corresponds to one trace.
		 Only one x-label provided. '''
		
		self.zscore_data = y_data
		self.zscore_labels = legend_labels
		self.zscore_x_data = x_data
		self.zscore_x_label = x_label
	
	def is_active(self):
		return self._is_active
	
	def set_active(self, b:bool):
		self._is_active = b
		self.plot_data()
	
	def plot_data(self):
		''' If the plot needs to be updated (active and out of date) re-renders the graph and displays it. '''
		
		if self.is_active() and (not self.plot_is_current):
			self.render_plot()
	
	def calc_mask(self):
		return None
	
	def get_condition(self, c:str):
		
		if c in self.conditions:
			return self.conditions[c]
		elif c in self.gcond:
			return self.gcond[c]
		else:
			return None
	
	def get_fig_if_active(self):
		
		# Return if not active
		if not self.is_active():
			return None
		
		return self.fig_list
	
	def plot_zscore_if_active(self):
		''' Generates a Z-Score breakout window if window is active and if z-score window is possible. Requires:
		* calc_mask must be overridden
		* init_zscore_data must have been called.'''
		
		# Return if not active
		if not self.is_active():
			return
		
		# Return if no z-score data provided
		if len(self.zscore_data) == 0 or len(self.zscore_labels) == 0:
			self.log.info("Active plot is not showing Z-score because data was not provided.")
			return
		
		# Return if no mask
		mask = self.calc_mask()
		if mask is None:
			self.log.info("Active plot is not showing Z-score because calc_mask() was not overridden.")
			return
		
		# Create masked y-data
		y_data = []
		for zsd in self.zscore_data:
			y_data.append(zsd[mask])
		
		# Create default X values if not provided
		x_data = []
		if len(self.zscore_x_data) == 0:
			for yd in y_data:
				x_data.append(list(range(0, len(zsd))))
		else:
			for xd in self.zscore_x_data:
				x_data.append(xd[mask])
			
		self.zscore_dialog = ZScorePlotWindow(x_data, y_data, self.zscore_labels, self.zscore_x_label)
		self.zscore_dialog.show()
	
	def update_plot(self):
		''' Marks the plot to be updated eventually. '''
		
		# Indicate need to replot
		self.plot_is_current = False
		
		self.plot_data()
		
	@abstractmethod
	def manual_init(self):
		pass
	
	@abstractmethod
	def render_plot(self):
		pass

def updateRenderPB(func):
	def wrapper(*args, **kwargs):
		if args[0].mdata.dlm.main_window is not None:
			args[0].mdata.dlm.main_window.status_bar.setRendering(True)
			args[0].mdata.dlm.main_window.app.processEvents()
		func(*args, **kwargs)
		if args[0].mdata.dlm.main_window is not None:
			args[0].mdata.dlm.main_window.status_bar.setRendering(False)
		
	return wrapper

class HarmGenFreqDomainPlotWidget(TabPlotWidget):
	
	def __init__(self, global_conditions:dict, log:LogPile, mdata:MasterData):
		super().__init__(global_conditions, log, mdata)
		
		# Conditions dictionaries
		self.conditions = {'rounding_step1': 0.1, 'rounding_step2': 0.01}
		
		self.manual_init()
		
		# Create figure
		self.fig1, self.ax1 = plt.subplots(1, 1)
		self.fig_list.append(self.fig1)
		
		# Estimate system Z
		expected_Z = self.mdata.MFLI_V_offset_V[1]/(self.mdata.requested_Idc_mA[1]/1e3) #TODO: Do something more general than index 1
		system_Z = self.mdata.MFLI_V_offset_V/(mdata.Idc_mA/1e3)
		self.extra_z = system_Z - expected_Z
		
		self.render_plot()
		
		# Create widgets
		self.fig1c = FigureCanvas(self.fig1)
		self.toolbar1 = NavigationToolbar2QT(self.fig1c, self)
		
		# Add widgets to parent-widget and set layout
		self.grid = QtWidgets.QGridLayout()
		self.grid.addWidget(self.toolbar1, 0, 0)
		self.grid.addWidget(self.fig1c, 1, 0)
		self.setLayout(self.grid)
	
	def manual_init(self, is_reinit:bool=False):
		self.init_zscore_data([self.mdata.zs_rf1, self.mdata.zs_rf2, self.mdata.zs_rf3], ['Fundamental', '2nd Harmonic', '3rd Harmonic'], [self.mdata.freq_rf_GHz, self.mdata.freq_rf_GHz, self.mdata.freq_rf_GHz], "Frequency (GHz)")
		
		if is_reinit:
			if self.get_condition(GCOND_REMOVE_OUTLIERS):
				mask = np.array(self.mdata.outlier_mask)
			if not np.any(mask):
				self.log.warning(f"No points matched when calculating mask for graph limits. Aborting graph limit calculation.")
				return
		else:
			mask = np.full(len(self.mdata.rf3), True)
		
		self.ylims1 = get_graph_lims(np.concatenate((self.mdata.rf1[mask], self.mdata.rf2[mask], self.mdata.rf3[mask])), step=10)
		self.xlims1 = get_graph_lims(self.mdata.freq_rf_GHz[mask], step=0.5)
		
	def calc_mask(self):
		b = self.get_condition('sel_bias_mA')
		p = self.get_condition('sel_power_dBm')
		
		# Filter relevant data
		mask_bias = (self.mdata.requested_Idc_mA == b)
		mask_pwr = (self.mdata.power_rf_dBm == p)
		loc_mask = (mask_bias & mask_pwr)
		
		if self.get_condition(GCOND_REMOVE_OUTLIERS):
			mask = np.array(loc_mask) & np.array(self.mdata.outlier_mask)
			self.log.lowdebug(f"Removing outliers. Mask had {loc_mask.sum()} vals, now {mask.sum()} vals.")
		else:
			self.log.lowdebug(f"Ignoring outlier spec")
			mask = loc_mask
		
		return mask
	
	@updateRenderPB
	def render_plot(self):
		use_fund = self.get_condition(GCOND_FREQXAXIS_ISFUND)
		b = self.get_condition('sel_bias_mA')
		p = self.get_condition('sel_power_dBm')
		
		# Filter relevant data
		mask = self.calc_mask()
			
		# Plot results
		self.ax1.cla()
		
		# Check correct number of points
		mask_len = np.sum(mask)
		# if len(self.mdata.unique_freqs) != mask_len:
		# 	log.warning(f"Cannot display data: Mismatched number of points (bias = {b} mA, pwr = {p} dBm, mask: {mask_len}, freq: {len(self.mdata.unique_freqs)})")
		# 	self.fig1.canvas.draw_idle()
		# 	return
		
		if use_fund:
			self.ax1.plot(self.mdata.freq_rf_GHz[mask], self.mdata.rf1[mask], linestyle=':', marker='o', markersize=4, color=(0, 0.7, 0))
			self.ax1.plot(self.mdata.freq_rf_GHz[mask], self.mdata.rf2[mask], linestyle=':', marker='o', markersize=4, color=(0, 0, 0.7))
			self.ax1.plot(self.mdata.freq_rf_GHz[mask], self.mdata.rf3[mask], linestyle=':', marker='o', markersize=4, color=(0.7, 0, 0))
			self.ax1.set_xlabel("Fundamental Frequency (GHz)")
		else:
			self.ax1.plot(self.mdata.freq_rf_GHz[mask], self.mdata.rf1[mask], linestyle=':', marker='o', markersize=4, color=(0, 0.7, 0))
			self.ax1.plot(self.mdata.freq_rf_GHz[mask]*2, self.mdata.rf2[mask], linestyle=':', marker='o', markersize=4, color=(0, 0, 0.7))
			self.ax1.plot(self.mdata.freq_rf_GHz[mask]*3, self.mdata.rf3[mask], linestyle=':', marker='o', markersize=4, color=(0.7, 0, 0))
			self.ax1.set_xlabel("Tone Frequency (GHz)")
			
		self.ax1.set_title(f"Bias = {b} mA, p = {p} dBm")
		self.ax1.set_ylabel("Power (dBm)")
		self.ax1.legend(["Fundamental", "2nd Harm.", "3rd Harm."])
		self.ax1.grid(True)
		
		if self.get_condition('fix_scale'):
			self.ax1.set_ylim(self.ylims1)
			if use_fund:
				self.ax1.set_xlim(self.xlims1)
			else:
				self.ax1.set_xlim((self.xlims1[0], self.xlims1[1]*3))
		self.fig1.tight_layout()
		
		self.fig1.canvas.draw_idle()
		
		self.plot_is_current = True

class CE23FreqDomainPlotWidget(TabPlotWidget):
	
	def __init__(self, global_conditions:dict, log:LogPile, mdata:MasterData):
		super().__init__(global_conditions, log, mdata)
		
		# Conditions dictionaries
		self.conditions = {'rounding_step1': 0.1, 'rounding_step2': 0.01}
		
		self.manual_init()
		
		# Create figure
		self.fig1, self.ax1 = plt.subplots(1, 1)
		self.fig2, self.ax2 = plt.subplots(1, 1)
		self.fig_list.append(self.fig1)
		self.fig_list.append(self.fig2)
		
		# Estimate system Z
		expected_Z = self.mdata.MFLI_V_offset_V[1]/(self.mdata.requested_Idc_mA[1]/1e3) #TODO: Do something more general than index 1
		system_Z = self.mdata.MFLI_V_offset_V/(self.mdata.Idc_mA/1e3)
		self.extra_z = system_Z - expected_Z
		
		
		self.render_plot()
		
		# Create widgets
		self.fig1c = FigureCanvas(self.fig1)
		self.toolbar1 = NavigationToolbar2QT(self.fig1c, self)
		self.fig2c = FigureCanvas(self.fig2)
		self.toolbar2 = NavigationToolbar2QT(self.fig2c, self)
		
		# Add widgets to parent-widget and set layout
		self.grid = QtWidgets.QGridLayout()
		self.grid.addWidget(self.toolbar1, 0, 0)
		self.grid.addWidget(self.fig1c, 1, 0)
		self.grid.addWidget(self.toolbar2, 0, 1)
		self.grid.addWidget(self.fig2c, 1, 1)
		self.setLayout(self.grid)
	
	def manual_init(self, is_reinit:bool=False):
		
		self.init_zscore_data([self.mdata.zs_ce2, self.mdata.zs_ce3], ["2f0 Conversion Efficiency", "3f0 Conversion Efficiency"], [self.mdata.freq_rf_GHz, self.mdata.freq_rf_GHz], "Frequency (GHz)")
		
		if is_reinit:
			if self.get_condition(GCOND_REMOVE_OUTLIERS):
				mask = np.array(self.mdata.outlier_mask)
			if not np.any(mask):
				self.log.warning(f"No points matched when calculating mask for graph limits. Aborting graph limit calculation.")
				return
		else:
			mask = np.full(len(self.mdata.ce2), True)
		
		self.ylims1 = get_graph_lims(self.mdata.ce2[mask], 5)
		self.ylims2 = get_graph_lims(self.mdata.ce3[mask], 0.5)
		
		self.xlimsX = get_graph_lims(self.mdata.freq_rf_GHz[mask], 0.5)
	
	def calc_mask(self):
		b = self.get_condition('sel_bias_mA')
		p = self.get_condition('sel_power_dBm')
		
		# Filter relevant data
		mask_bias = (self.mdata.requested_Idc_mA == b)
		mask_pwr = (self.mdata.power_rf_dBm == p)
		loc_mask = (mask_bias & mask_pwr)
	
		if self.get_condition(GCOND_REMOVE_OUTLIERS):
			mask = np.array(loc_mask) & np.array(self.mdata.outlier_mask)
			self.log.lowdebug(f"Removing outliers. Mask had {loc_mask.sum()} vals, now {mask.sum()} vals.")
		else:
			self.log.lowdebug(f"Ignoring outlier spec")
			mask = loc_mask
		
		return mask
	
	@updateRenderPB
	def render_plot(self):
		b = self.get_condition('sel_bias_mA')
		p = self.get_condition('sel_power_dBm')
		use_fund = self.get_condition(GCOND_FREQXAXIS_ISFUND)
		
		# Filter relevant data
		mask = self.calc_mask()
		
		# Plot results
		self.ax1.cla()
		self.ax2.cla()
		
		if not self.mdata.is_valid_sweep():
			self.log.debug(f"Invalid sweep data. Aborting plot.")
			return
		
		if use_fund:
			self.ax1.plot(self.mdata.freq_rf_GHz[mask], self.mdata.ce2[mask], linestyle=':', marker='o', markersize=4, color=(0.6, 0, 0.7))
			self.ax2.plot(self.mdata.freq_rf_GHz[mask], self.mdata.ce3[mask], linestyle=':', marker='o', markersize=4, color=(0.45, 0.05, 0.1))
			self.ax1.set_xlabel("Fundamental Frequency (GHz)")
			self.ax2.set_xlabel("Fundamental Frequency (GHz)")
		else:
			self.ax1.plot(self.mdata.freq_rf_GHz[mask]*2, self.mdata.ce2[mask], linestyle=':', marker='o', markersize=4, color=(0.6, 0, 0.7))
			self.ax2.plot(self.mdata.freq_rf_GHz[mask]*3, self.mdata.ce3[mask], linestyle=':', marker='o', markersize=4, color=(0.45, 0.05, 0.1))
			self.ax1.set_xlabel("2nd Harmonic Frequency (GHz)")
			self.ax2.set_xlabel("3rd Harmonic Frequency (GHz)")
			
		self.ax1.set_title(f"Bias = {b} mA, p = {p} dBm")
		self.ax1.set_ylabel("2nd Harm. Conversion Efficiency (%)")
		self.ax1.grid(True)
		
		self.ax2.set_title(f"Bias = {b} mA, p = {p} dBm")
		self.ax2.set_ylabel("3rd Harm. Conversion Efficiency (%)")
		self.ax2.grid(True)
		
		if self.get_condition('fix_scale'):
			self.ax1.set_ylim(self.ylims1)
			self.ax2.set_ylim(self.ylims2)
			
			if use_fund:
				self.ax1.set_xlim(self.xlimsX)
				self.ax2.set_xlim(self.xlimsX)
			else:
				self.ax1.set_xlim((self.xlimsX[0]*2, self.xlimsX[1]*2))
				self.ax2.set_xlim((self.xlimsX[0]*3, self.xlimsX[1]*3))
				
		self.fig1.tight_layout()
		self.fig2.tight_layout()
		
		self.fig1.canvas.draw_idle()
		self.fig2.canvas.draw_idle()
		
		self.plot_is_current = True

class CE23BiasDomainPlotWidget(TabPlotWidget):
	
	def __init__(self, global_conditions:dict, log:LogPile, mdata:MasterData):
		super().__init__(global_conditions, log, mdata)
		
		# Conditions dictionaries
		self.conditions = {'rounding_step1': 0.1, 'rounding_step2': 0.01}
		
		self.manual_init()
		
		# Create figure
		self.fig1, self.ax1 = plt.subplots(1, 1)
		self.fig2, self.ax2 = plt.subplots(1, 1)
		self.fig_list.append(self.fig1)
		self.fig_list.append(self.fig2)
		
		# Estimate system Z
		expected_Z = self.mdata.MFLI_V_offset_V[1]/(self.mdata.requested_Idc_mA[1]/1e3) #TODO: Do something more general than index 1
		system_Z = self.mdata.MFLI_V_offset_V/(self.mdata.Idc_mA/1e3)
		self.extra_z = system_Z - expected_Z
		
		
		self.render_plot()
		
		# Create widgets
		self.fig1c = FigureCanvas(self.fig1)
		self.toolbar1 = NavigationToolbar2QT(self.fig1c, self)
		self.fig2c = FigureCanvas(self.fig2)
		self.toolbar2 = NavigationToolbar2QT(self.fig2c, self)
		
		# Add widgets to parent-widget and set layout
		self.grid = QtWidgets.QGridLayout()
		self.grid.addWidget(self.toolbar1, 0, 0)
		self.grid.addWidget(self.fig1c, 1, 0)
		self.grid.addWidget(self.toolbar2, 0, 1)
		self.grid.addWidget(self.fig2c, 1, 1)
		self.setLayout(self.grid)
	
	def manual_init(self, is_reinit:bool=False):
		
		self.init_zscore_data([self.mdata.zs_ce2, self.mdata.zs_ce3], ["2f0 Conversion Efficiency", "3f0 Conversion Efficiency"], [self.mdata.requested_Idc_mA, self.mdata.requested_Idc_mA], "Bias Current (mA)")
		
		if is_reinit:
			if self.get_condition(GCOND_REMOVE_OUTLIERS):
				mask = np.array(self.mdata.outlier_mask)
			if not np.any(mask):
				self.log.warning(f"No points matched when calculating mask for graph limits. Aborting graph limit calculation.")
				return
		else:
			mask = np.full(len(self.mdata.ce2), True)
		
		self.ylims1 = get_graph_lims(self.mdata.ce2[mask], 5)
		self.ylims2 = get_graph_lims(self.mdata.ce3[mask], 0.5)
		
		self.xlimsXr = get_graph_lims(self.mdata.requested_Idc_mA[mask], 0.25)
		self.xlimsXm = get_graph_lims(self.mdata.Idc_mA[mask], 0.25)
		
	def calc_mask(self):
		f = self.get_condition('sel_freq_GHz')
		p = self.get_condition('sel_power_dBm')
		
		# Filter relevant data
		mask_freq = (self.mdata.freq_rf_GHz == f)
		mask_pwr = (self.mdata.power_rf_dBm == p)
		loc_mask = (mask_freq & mask_pwr)
		
		if self.get_condition(GCOND_REMOVE_OUTLIERS):
			mask = np.array(loc_mask) & np.array(self.mdata.outlier_mask)
			self.log.lowdebug(f"Removing outliers. Mask had {loc_mask.sum()} vals, now {mask.sum()} vals.")
		else:
			self.log.lowdebug(f"Ignoring outlier spec")
			mask = loc_mask
		
		return mask
	
	@updateRenderPB
	def render_plot(self):
		
		f = self.get_condition('sel_freq_GHz')
		p = self.get_condition('sel_power_dBm')
		
		# Filter relevant data
		mask = self.calc_mask()
		
		# Plot results
		self.ax1.cla()
		self.ax2.cla()
		
		if not self.mdata.is_valid_sweep():
			self.log.debug(f"Invalid sweep data. Aborting plot.")
			return
		
		if self.get_condition(GCOND_BIASXAXIS_ISMEAS):
			self.ax1.plot(self.mdata.Idc_mA[mask], self.mdata.ce2[mask], linestyle=':', marker='o', markersize=4, color=(0.6, 0, 0.7))
			self.ax2.plot(self.mdata.Idc_mA[mask], self.mdata.ce3[mask], linestyle=':', marker='o', markersize=4, color=(0.45, 0.05, 0.1))
			self.ax1.set_xlabel("Measured DC Bias (mA)")
			self.ax2.set_xlabel("Measured DC Bias (mA)")
		else:
			self.ax1.plot(self.mdata.requested_Idc_mA[mask], self.mdata.ce2[mask], linestyle=':', marker='o', markersize=4, color=(0.6, 0, 0.7))
			self.ax2.plot(self.mdata.requested_Idc_mA[mask], self.mdata.ce3[mask], linestyle=':', marker='o', markersize=4, color=(0.45, 0.05, 0.1))
			self.ax1.set_xlabel("Requested DC Bias (mA)")
			self.ax2.set_xlabel("Requested DC Bias (mA)")
			
		self.ax1.set_title(f"f-fund = {f} GHz, f-harm2 = {rd(2*f)} GHz, p = {p} dBm")
		self.ax1.set_ylabel("2nd Harm. Conversion Efficiency (%)")
		self.ax1.grid(True)
		
		self.ax2.set_title(f"f-fund = {f} GHz, f-harm3 = {rd(3*f)} GHz, p = {p} dBm")
		self.ax2.set_ylabel("3rd Harm. Conversion Efficiency (%)")
		self.ax2.grid(True)
		
		if self.get_condition('fix_scale'):
			self.ax1.set_ylim(self.ylims1)
			self.ax2.set_ylim(self.ylims2)
			
			if self.get_condition(GCOND_BIASXAXIS_ISMEAS):
				self.ax1.set_xlim(self.xlimsXr)
				self.ax2.set_xlim(self.xlimsXr)
			else:
				self.ax1.set_xlim(self.xlimsXm)
				self.ax2.set_xlim(self.xlimsXm)
		
		self.fig1.tight_layout()
		self.fig2.tight_layout()
		
		self.fig1.canvas.draw_idle()
		self.fig2.canvas.draw_idle()
		
		self.plot_is_current = True

class IVPlotWidget(TabPlotWidget):
	
	def __init__(self, global_conditions:dict, log:LogPile, mdata:MasterData):
		super().__init__(global_conditions, log, mdata)
		
		# Conditions dictionaries
		self.conditions = self.conditions = {'rounding_step1': 0.1, 'rounding_step2': 0.01, 'rounding_step_x1b':0.05}
		
		# Create figure
		self.fig1, ax_arr1 = plt.subplots(2, 1)
		self.fig2, ax_arr2 = plt.subplots(2, 1)
		self.fig_list.append(self.fig1)
		self.fig_list.append(self.fig2)
		self.ax1t = ax_arr1[0]
		self.ax1b = ax_arr1[1]
		self.ax2t = ax_arr2[0]
		self.ax2b = ax_arr2[1]
		
		self.manual_init()
		
		self.render_plot()
		
		# Create widgets
		self.fig1c = FigureCanvas(self.fig1)
		self.toolbar1 = NavigationToolbar2QT(self.fig1c, self)
		self.fig2c = FigureCanvas(self.fig2)
		self.toolbar2 = NavigationToolbar2QT(self.fig2c, self)
		
		# Add widgets to parent-widget and set layout
		self.grid = QtWidgets.QGridLayout()
		self.grid.addWidget(self.toolbar1, 0, 0)
		self.grid.addWidget(self.fig1c, 1, 0)
		self.grid.addWidget(self.toolbar2, 0, 1)
		self.grid.addWidget(self.fig2c, 1, 1)
		self.setLayout(self.grid)
		
	def manual_init(self, is_reinit:bool=False):
		
		# # Estimate system Z
		# expected_Z = self.mdata.MFLI_V_offset_V[1]/(self.mdata.requested_Idc_mA[1]/1e3) #TODO: Do something more general than index 1
		# system_Z = self.mdata.MFLI_V_offset_V/(self.mdata.Idc_mA/1e3)
		# self.extra_z = system_Z - expected_Z
		
		# self.zs_extra_z = calc_zscore(self.extra_z)
		# self.zs_meas_Idc = calc_zscore(self.mdata.Idc_mA)
		
		self.init_zscore_data( [self.mdata.zs_extra_z, self.mdata.zs_meas_Idc], ['Extra Impedance', 'Measured Idc'], [self.mdata.requested_Idc_mA, self.mdata.requested_Idc_mA], 'Requested DC Bias (mA)' )
		
		if is_reinit:
			if self.get_condition(GCOND_REMOVE_OUTLIERS):
				mask = np.array(self.mdata.outlier_mask)
			if not np.any(mask):
				self.log.warning(f"No points matched when calculating mask for graph limits. Aborting graph limit calculation.")
				return
		else:
			mask = np.full(len(self.mdata.Idc_mA), True)
		
		self.ylim1 = get_graph_lims(self.mdata.Idc_mA[mask], 0.25)
		self.ylim2 = get_graph_lims(self.mdata.extra_z[mask], 50)
		self.xlimT = get_graph_lims(self.mdata.requested_Idc_mA[mask], 0.25)
		self.xlim1b = get_graph_lims(self.mdata.MFLI_V_offset_V[mask], 0.1)
		self.xlim2b = self.ylim1
		
	
	def calc_mask(self):
		f = self.get_condition('sel_freq_GHz')
		p = self.get_condition('sel_power_dBm')
		
		# Filter relevant data
		mask_freq = (self.mdata.freq_rf_GHz == f)
		mask_pwr = (self.mdata.power_rf_dBm == p)
		loc_mask = (mask_freq & mask_pwr)
	
		if self.get_condition(GCOND_REMOVE_OUTLIERS):
			mask = np.array(loc_mask) & np.array(self.mdata.outlier_mask)
			self.log.lowdebug(f"Removing outliers. Mask had {loc_mask.sum()} vals, now {mask.sum()} vals.")
		else:
			self.log.lowdebug(f"Ignoring outlier spec")
			mask = loc_mask
		
		return mask
	
	@updateRenderPB
	def render_plot(self):
		f = self.get_condition('sel_freq_GHz')
		p = self.get_condition('sel_power_dBm')
		
		# Filter relevant data
		mask = self.calc_mask()
		
		# Plot results
		self.ax1t.cla()
		self.ax1b.cla()
		self.ax2t.cla()
		self.ax2b.cla()
		
		if not self.mdata.is_valid_sweep():
			self.log.debug(f"Invalid sweep data. Aborting plot.")
			return
		
		# Check correct number of points
		mask_len = np.sum(mask)
		if (mask_len) == 0:
			self.log.debug(f"No data met slider conditions. Aborting render.")
			return
		
		# if len(self.mdata.unique_bias) != mask_len:
		# 	log.warning(f"Cannot display data: Mismatched number of points (freq = {f} GHz, pwr = {p} dBm, mask: {mask_len}, bias: {len(self.mdata.unique_bias)})")
		# 	self.fig1.canvas.draw_idle()
		# 	returnz
		
		minval = np.min([0, np.min(self.mdata.requested_Idc_mA[mask]), np.min(self.mdata.Idc_mA[mask]) ])
		maxval = np.max([0, np.max(self.mdata.requested_Idc_mA[mask]), np.max(self.mdata.Idc_mA[mask]) ])
		
		self.ax1t.plot(self.mdata.requested_Idc_mA[mask], self.mdata.Idc_mA[mask], linestyle=':', marker='o', markersize=4, color=(0.6, 0, 0.7), label="Measured")
		self.ax1t.plot([minval, maxval], [minval, maxval], linestyle='-', color=(0.8, 0, 0), linewidth=0.5, label="1:1 ratio")
		self.ax1b.plot(self.mdata.MFLI_V_offset_V[mask], self.mdata.Idc_mA[mask], linestyle=':', marker='s', markersize=4, color=(0.2, 0, 0.8))
		
		self.ax2t.plot(self.mdata.requested_Idc_mA[mask], self.mdata.extra_z[mask], linestyle=':', marker='o', markersize=4, color=(0.45, 0.5, 0.1))
		self.ax2b.plot(self.mdata.Idc_mA[mask], self.mdata.extra_z[mask], linestyle=':', marker='o', markersize=4, color=(0, 0.5, 0.8))
		
		self.ax1t.set_title(f"f = {f} GHz, p = {p} dBm")
		self.ax1t.legend()
		self.ax1t.set_xlabel("Requested DC Bias (mA)")
		self.ax1t.set_ylabel("Measured DC Bias (mA)")
		self.ax1t.grid(True)
		
			
		self.ax1b.set_title(f"f = {f} GHz, p = {p} dBm")
		self.ax1b.set_xlabel("Applied DC Voltage (V)")
		self.ax1b.set_ylabel("Measured DC Bias (mA)")
		self.ax1b.grid(True)
			
		
		self.ax2t.set_title(f"f = {f} GHz, p = {p} dBm")
		self.ax2t.set_xlabel("Requested DC Bias (mA)")
		self.ax2t.set_ylabel("Additional Impedance (Ohms)")
		self.ax2t.grid(True)
		
		self.ax2b.set_title(f"f = {f} GHz, p = {p} dBm")
		self.ax2b.set_xlabel("Measured DC Bias (mA)")
		self.ax2b.set_ylabel("Additional Impedance (Ohms)")
		self.ax2b.grid(True)
		
		if self.get_condition('fix_scale'):
			self.ax1t.set_ylim(self.ylim1)
			self.ax1b.set_ylim(self.ylim1)
			
			self.ax2t.set_ylim(self.ylim2)
			self.ax2b.set_ylim(self.ylim2)
			
			self.ax1t.set_xlim(self.xlimT)
			self.ax2t.set_xlim(self.xlimT)
			self.ax1b.set_xlim(self.xlim1b)
			self.ax2b.set_xlim(self.xlim2b)
		
		self.fig1.tight_layout()
		self.fig2.tight_layout()
		
		self.fig1.canvas.draw_idle()
		self.fig2.canvas.draw_idle()
		
		self.plot_is_current = True

class SParamSPDPlotWidget(TabPlotWidget):
	
	def __init__(self, global_conditions:dict, log:LogPile, mdata:MasterData):
		super().__init__(global_conditions, log, mdata)
		
		# Conditions dictionaries
		self.conditions = {'rounding_step':10}
		
		self.manual_init()
		
		# Create figure
		self.fig1, self.ax1 = plt.subplots(1, 1, figsize=(12, 7))
		self.fig1.subplots_adjust(left=0.065, bottom=0.065, top=0.95, right=0.8)
		self.fig_list.append(self.fig1)
		
		self.render_plot()
		
		# Create widgets
		self.fig1c = FigureCanvas(self.fig1)
		self.toolbar = NavigationToolbar2QT(self.fig1c, self)
		
		# Add widgets to parent-widget and set layout
		self.grid = QtWidgets.QGridLayout()
		self.grid.addWidget(self.toolbar, 0, 0)
		self.grid.addWidget(self.fig1c, 1, 0)
		self.setLayout(self.grid)
	
	def manual_init(self, is_reinit:bool=False):
		pass
		# # Get autoscale choices
		# umax = np.max([np.max(self.mdata.rf1), np.max(self.mdata.rf2), np.max(self.mdata.rf3)])
		# umin = np.min([np.min(self.mdata.rf1), np.min(self.mdata.rf2), np.min(self.mdata.rf3)])
		
		# rstep = self.get_condition('rounding_step')
		# if rstep is None:
		# 	rstep = 10
		
		# self.ylims = [np.floor(umin/rstep)*rstep, np.ceil(umax/rstep)*rstep]
	
	@updateRenderPB
	def render_plot(self):
		# f = self.get_condition('sel_freq_GHz')
		# p = self.get_condition('sel_power_dBm')
		
		# # Filter relevant data
		# mask_freq = (self.mdata.freq_rf_GHz == f)
		# mask_pwr = (self.mdata.power_rf_dBm == p)
		# mask = (mask_freq & mask_pwr)
		
		# Plot results
		self.ax1.cla()
		
		if not self.mdata.is_valid_sweep():
			self.log.debug(f"Invalid sweep data. Aborting plot.")
			return
		
		# Check correct number of points
		# mask_len = np.sum(mask)
		# if len(self.self.mdata.unique_bias) != mask_len:
		# 	log.warning(f"Cannot display data: Mismatched number of points (freq = {f} GHz, pwr = {p} dBm, mask: {mask_len}, bias: {len(self.self.mdata.unique_bias)})")
		# 	self.fig1.canvas.draw_idle()
		# 	return
		
		
		self.ax1.plot(self.mdata.S_freq_GHz, self.mdata.S11_dB, linestyle=':', marker='o', markersize=1, color=(0.7, 0, 0))
		self.ax1.plot(self.mdata.S_freq_GHz, self.mdata.S21_dB, linestyle=':', marker='o', markersize=1, color=(0, 0.7, 0))
		
		if self.get_condition('sparam_show_sum'):
			self.ax1.plot(self.mdata.S_freq_GHz, lin_to_dB(np.abs(self.mdata.S11+self.mdata.S21)), linestyle=':', marker='.', markersize=1, color=(0.7, 0.7, 0))
			self.ax1.legend(["S11", "S21", "S11+S21"])
		else:
			self.ax1.legend(["S11", "S21"])	
		# self.ax1.set_title(f"f = {f} GHz, p = {p} dBm")
		self.ax1.set_xlabel("Frequency (GHz)")
		self.ax1.set_ylabel("Power (dBm)")
		
		self.ax1.grid(True)
		
		# if self.get_condition('fix_scale'):
		# 	self.ax1.set_ylim(self.ylims)
		
		self.fig1.tight_layout()
		
		self.fig1.canvas.draw_idle()
		
		self.plot_is_current = True

class HarmGenBiasDomainPlotWidget(TabPlotWidget):
	
	def __init__(self, global_conditions:dict, log:LogPile, mdata:MasterData):
		super().__init__(global_conditions, log, mdata)
		
		# Conditions dictionaries
		self.conditions = {'rounding_step':10}
		
		self.manual_init()
		
		# Create figure
		self.fig1, self.ax1 = plt.subplots(1, 1, figsize=(12, 7))
		self.fig1.subplots_adjust(left=0.065, bottom=0.065, top=0.95, right=0.8)
		self.fig_list.append(self.fig1)
		
		self.render_plot()
		
		# Create widgets
		self.fig1c = FigureCanvas(self.fig1)
		self.toolbar = NavigationToolbar2QT(self.fig1c, self)
		
		# Add widgets to parent-widget and set layout
		self.grid = QtWidgets.QGridLayout()
		self.grid.addWidget(self.toolbar, 0, 0)
		self.grid.addWidget(self.fig1c, 1, 0)
		self.setLayout(self.grid)
	
	def calc_mask(self):
		f = self.get_condition('sel_freq_GHz')
		p = self.get_condition('sel_power_dBm')
		
		# Filter relevant data
		mask_freq = (self.mdata.freq_rf_GHz == f)
		mask_pwr = (self.mdata.power_rf_dBm == p)
		loc_mask = (mask_freq & mask_pwr)
	
		if self.get_condition(GCOND_REMOVE_OUTLIERS):
			mask = np.array(loc_mask) & np.array(self.mdata.outlier_mask)
			self.log.lowdebug(f"Removing outliers. Mask had {loc_mask.sum()} vals, now {mask.sum()} vals.")
		else:
			self.log.lowdebug(f"Ignoring outlier spec")
			mask = loc_mask
		
		return mask
	
	def manual_init(self, is_reinit:bool=False):
		
		self.init_zscore_data([self.mdata.zs_rf1, self.mdata.zs_rf2, self.mdata.zs_rf3], ['Fundamental', '2nd Harmonic', '3rd Harmonic'], [self.mdata.Idc_mA, self.mdata.Idc_mA, self.mdata.Idc_mA], "Bias Current (mA)")
		
		if is_reinit:
			if self.get_condition(GCOND_REMOVE_OUTLIERS):
				mask = np.array(self.mdata.outlier_mask)
			if not np.any(mask):
				self.log.warning(f"No points matched when calculating mask for graph limits. Aborting graph limit calculation.")
				return
		else:
			mask = np.full(len(self.mdata.rf1), True)
		
		self.ylims1 = get_graph_lims(np.concatenate((self.mdata.rf1[mask], self.mdata.rf2[mask], self.mdata.rf3[mask])), step=10)
		self.xlims1m = get_graph_lims(self.mdata.Idc_mA[mask], step=0.25)
		self.xlims1r = get_graph_lims(self.mdata.requested_Idc_mA[mask], step=0.25)
	
	@updateRenderPB
	def render_plot(self):
		f = self.get_condition('sel_freq_GHz')
		p = self.get_condition('sel_power_dBm')
		
		# Filter relevant data
		mask = self.calc_mask()
		
		# Plot results
		self.ax1.cla()
		
		if not self.mdata.is_valid_sweep():
			self.log.debug(f"Invalid sweep data. Aborting plot.")
			return
		
		if self.get_condition(GCOND_BIASXAXIS_ISMEAS):
			self.ax1.plot(self.mdata.Idc_mA[mask], self.mdata.rf1[mask], linestyle=':', marker='o', markersize=4, color=(0, 0.7, 0))
			self.ax1.plot(self.mdata.Idc_mA[mask], self.mdata.rf2[mask], linestyle=':', marker='o', markersize=4, color=(0, 0, 0.7))
			self.ax1.plot(self.mdata.Idc_mA[mask], self.mdata.rf3[mask], linestyle=':', marker='o', markersize=4, color=(0.7, 0, 0))
			self.ax1.set_xlabel("Measured DC Bias (mA)")
		else:
			self.ax1.plot(self.mdata.requested_Idc_mA[mask], self.mdata.rf1[mask], linestyle=':', marker='o', markersize=4, color=(0, 0.7, 0))
			self.ax1.plot(self.mdata.requested_Idc_mA[mask], self.mdata.rf2[mask], linestyle=':', marker='o', markersize=4, color=(0, 0, 0.7))
			self.ax1.plot(self.mdata.requested_Idc_mA[mask], self.mdata.rf3[mask], linestyle=':', marker='o', markersize=4, color=(0.7, 0, 0))
			self.ax1.set_xlabel("Requested DC Bias (mA)")
			
		self.ax1.set_title(f"f = {f} GHz, p = {p} dBm")
		self.ax1.set_ylabel("Power (dBm)")
		self.ax1.legend(["Fundamental", "2nd Harm.", "3rd Harm."])
		self.ax1.grid(True)
		
		if self.get_condition('fix_scale'):
			self.ax1.set_ylim(self.ylims1)
			
			if self.get_condition(GCOND_BIASXAXIS_ISMEAS):
				self.ax1.set_xlim(self.xlims1m)
			else:
				self.ax1.set_xlim(self.xlims1r)
				
		self.fig1.tight_layout()
		
		self.fig1.canvas.draw_idle()
		
		self.plot_is_current = True

# class MaxBiasBiasDomainPlotWidget(TabPlotWidget):
#	
#	def __init__(self, global_conditions:dict, log:LogPile, mdata:MasterData):
# 		super().__init__(global_conditions, log, mdata)
		
# 		# Conditions dictionaries
# 		self.conditions = {'rounding_step':10}
		
# 		self.manual_init()
		
# 		# Create figure
# 		self.fig1, self.ax1 = plt.subplots(1, 1, figsize=(12, 7))
# 		self.fig1.subplots_adjust(left=0.065, bottom=0.065, top=0.95, right=0.8)
# 		self.fig_list.append(self.fig1)
		
# 		self.render_plot()
		
# 		# Create widgets
# 		self.fig1c = FigureCanvas(self.fig1)
# 		self.toolbar = NavigationToolbar2QT(self.fig1c, self)
		
# 		# Add widgets to parent-widget and set layout
# 		self.grid = QtWidgets.QGridLayout()
# 		self.grid.addWidget(self.toolbar, 0, 0)
# 		self.grid.addWidget(self.fig1c, 1, 0)
# 		self.setLayout(self.grid)
#	
#	def calc_mask(self):
# 		f = self.get_condition('sel_freq_GHz')
# 		p = self.get_condition('sel_power_dBm')
		
# 		# Filter relevant data
# 		mask_freq = (self.mdata.freq_rf_GHz == f)
# 		mask_pwr = (self.mdata.power_rf_dBm == p)
# 		loc_mask = (mask_freq & mask_pwr)
	
# 		if self.get_condition(GCOND_REMOVE_OUTLIERS):
# 			mask = np.array(loc_mask) & np.array(self.mdata.outlier_mask)
# 			self.log.lowdebug(f"Removing outliers. Mask had {loc_mask.sum()} vals, now {mask.sum()} vals.")
# 		else:
# 			self.log.lowdebug(f"Ignoring outlier spec")
# 			mask = loc_mask
		
# 		return mask
#	
#	def manual_init(self, is_reinit:bool=False):
		
# 		self.init_zscore_data([self.mdata.zs_rf1, self.mdata.zs_rf2, self.mdata.zs_rf3], ['Fundamental', '2nd Harmonic', '3rd Harmonic'], [self.mdata.Idc_mA, self.mdata.Idc_mA, self.mdata.Idc_mA], "Bias Current (mA)")
		
# 		if is_reinit:
# 			if self.get_condition(GCOND_REMOVE_OUTLIERS):
# 				mask = np.array(self.mdata.outlier_mask)
# 			if not np.any(mask):
# 				self.log.warning(f"No points matched when calculating mask for graph limits. Aborting graph limit calculation.")
# 				return
# 		else:
# 			mask = np.full(len(self.mdata.rf1), True)
		
# 		self.ylims1 = get_graph_lims(np.concatenate((self.mdata.rf1[mask], self.mdata.rf2[mask], self.mdata.rf3[mask])), step=10)
# 		self.xlims1m = get_graph_lims(self.mdata.Idc_mA[mask], step=0.25)
# 		self.xlims1r = get_graph_lims(self.mdata.requested_Idc_mA[mask], step=0.25)
#	
#	@updateRenderPB
#	def render_plot(self):
# 		f = self.get_condition('sel_freq_GHz')
# 		p = self.get_condition('sel_power_dBm')
		
# 		# Filter relevant data
# 		mask = self.calc_mask()
		
# 		# Plot results
# 		self.ax1.cla()
		
# 		if not self.mdata.is_valid_sweep():
# 			self.log.debug(f"Invalid sweep data. Aborting plot.")
# 			return
		
# 		if self.get_condition(GCOND_BIASXAXIS_ISMEAS):
# 			self.ax1.plot(self.mdata.Idc_mA[mask], self.mdata.rf1[mask], linestyle=':', marker='o', markersize=4, color=(0, 0.7, 0))
# 			self.ax1.plot(self.mdata.Idc_mA[mask], self.mdata.rf2[mask], linestyle=':', marker='o', markersize=4, color=(0, 0, 0.7))
# 			self.ax1.plot(self.mdata.Idc_mA[mask], self.mdata.rf3[mask], linestyle=':', marker='o', markersize=4, color=(0.7, 0, 0))
# 			self.ax1.set_xlabel("Measured DC Bias (mA)")
# 		else:
# 			self.ax1.plot(self.mdata.requested_Idc_mA[mask], self.mdata.rf1[mask], linestyle=':', marker='o', markersize=4, color=(0, 0.7, 0))
# 			self.ax1.plot(self.mdata.requested_Idc_mA[mask], self.mdata.rf2[mask], linestyle=':', marker='o', markersize=4, color=(0, 0, 0.7))
# 			self.ax1.plot(self.mdata.requested_Idc_mA[mask], self.mdata.rf3[mask], linestyle=':', marker='o', markersize=4, color=(0.7, 0, 0))
# 			self.ax1.set_xlabel("Requested DC Bias (mA)")
			
# 		self.ax1.set_title(f"f = {f} GHz, p = {p} dBm")
# 		self.ax1.set_ylabel("Power (dBm)")
# 		self.ax1.legend(["Fundamental", "2nd Harm.", "3rd Harm."])
# 		self.ax1.grid(True)
		
# 		if self.get_condition('fix_scale'):
# 			self.ax1.set_ylim(self.ylims1)
			
# 			if self.get_condition(GCOND_BIASXAXIS_ISMEAS):
# 				self.ax1.set_xlim(self.xlims1m)
# 			else:
# 				self.ax1.set_xlim(self.xlims1r)
				
# 		self.fig1.tight_layout()
		
# 		self.fig1.canvas.draw_idle()
		
# 		self.plot_is_current = True

class SpectrumPIDomainPlotWidget(TabPlotWidget):
	
	ZOOM_MODE_FULL = 0
	ZOOM_MODE_FUND = 1
	ZOOM_MODE_2H = 2
	ZOOM_MODE_3H = 3
	
	def __init__(self, global_conditions:dict, log:LogPile, mdata:MasterData):
		super().__init__(global_conditions, log, mdata)
		
		# Conditions dictionaries
		self.conditions = {'rounding_step1': 0.1, 'rounding_step2': 0.01}
		
		self.manual_init()
		
		# Create figure
		self.fig1, self.ax1 = plt.subplots(1, 1)
		self.default_xlims = None
		self.zoom_mode = SpectrumPIDomainPlotWidget.ZOOM_MODE_FULL
		self.fig_list.append(self.fig1)
		
		# Estimate system Z
		expected_Z = self.mdata.MFLI_V_offset_V[1]/(self.mdata.requested_Idc_mA[1]/1e3) #TODO: Do something more general than index 1
		system_Z = self.mdata.MFLI_V_offset_V/(mdata.Idc_mA/1e3)
		self.extra_z = system_Z - expected_Z
		
		self.render_plot()
		
		# Create widgets
		self.fig1c = FigureCanvas(self.fig1)
		self.toolbar1 = NavigationToolbar2QT(self.fig1c, self)
		
		self.zoom_span_label = QLabel("Zoom Span: kHz")
		# self.zoom_span_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
		self.zoom_span_label.setFixedWidth(120)
		
		self.zoom_span_edit = QLineEdit()
		self.zoom_span_edit.setText("10")
		self.zoom_span_edit.setValidator(QDoubleValidator())
		self.zoom_span_edit.setFixedWidth(50)
		self.zoom_span_edit.editingFinished.connect(self._reapply_zoom)
		
		# self.right_spacer = QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
		
		# Make buttons
		self.fund_btn = QPushButton("Fundamental", parent=self)
		self.fund_btn.setFixedSize(100, 25)
		self.fund_btn.clicked.connect(self._zoom_fund)
		
		self.f2h_btn = QPushButton("2nd Harmonic", parent=self)
		self.f2h_btn.setFixedSize(100, 25)
		self.f2h_btn.clicked.connect(self._zoom_2h)
		
		self.f3h_btn = QPushButton("3rd Harmonic", parent=self)
		self.f3h_btn.setFixedSize(100, 25)
		self.f3h_btn.clicked.connect(self._zoom_3h)
		
		self.reset_btn = QPushButton("Full Span", parent=self)
		self.reset_btn.setFixedSize(100, 25)
		self.reset_btn.clicked.connect(self._zoom_reset)
		
		# Add widgets to parent-widget and set layout
		self.grid = QtWidgets.QGridLayout()
		self.grid.addWidget(self.toolbar1, 0, 0, 1, 7)
		self.grid.addWidget(self.fig1c, 1, 0, 1, 7)
		
		
		self.grid.addWidget(self.zoom_span_label, 2, 0)
		self.grid.addWidget(self.zoom_span_edit, 2, 1)
		
		# self.grid.addItem(self.right_spacer, 2, 0, 6)
		
		self.grid.addWidget(self.fund_btn, 2, 3)
		self.grid.addWidget(self.f2h_btn, 2, 4)
		self.grid.addWidget(self.f3h_btn, 2, 5)
		self.grid.addWidget(self.reset_btn, 2, 6)
		
		
		self.setLayout(self.grid)
	
	def _reapply_zoom(self):
		
		if self.zoom_mode == SpectrumPIDomainPlotWidget.ZOOM_MODE_FULL:
			self._zoom_reset()
		elif self.zoom_mode == SpectrumPIDomainPlotWidget.ZOOM_MODE_FUND:
			self._zoom_fund()
		elif self.zoom_mode == SpectrumPIDomainPlotWidget.ZOOM_MODE_2H:
			self._zoom_2h()
		elif self.zoom_mode == SpectrumPIDomainPlotWidget.ZOOM_MODE_3H:
			self._zoom_3h()
	
	def _zoom_freq(self, f_center_GHz:float):
		
		try:
			span_kHz = float(self.zoom_span_edit.text())
		except Exception as e:
			self.log.warning(f"Failed to interpret textbox. Defaulting to 10 kHz.", detail=f"{e}")
			span_kHz = 10
		half_span_GHz = span_kHz/2e6
		self.ax1.set_xlim([f_center_GHz-half_span_GHz, f_center_GHz+half_span_GHz])
		self.fig1.canvas.draw_idle()
	
	def _zoom_fund(self):
		f = self.get_condition('sel_freq_GHz')
		self._zoom_freq(f)
		self.zoom_mode = SpectrumPIDomainPlotWidget.ZOOM_MODE_FUND
	
	def _zoom_2h(self):
		f = self.get_condition('sel_freq_GHz')
		self._zoom_freq(2*f)
		self.zoom_mode = SpectrumPIDomainPlotWidget.ZOOM_MODE_2H
		
	def _zoom_3h(self):
		f = self.get_condition('sel_freq_GHz')
		self._zoom_freq(3*f)
		self.zoom_mode = SpectrumPIDomainPlotWidget.ZOOM_MODE_3H
		
	def _zoom_reset(self):
		self.zoom_mode = SpectrumPIDomainPlotWidget.ZOOM_MODE_FULL
		if self.default_xlims is not None:
			self.ax1.set_xlim(self.default_xlims)
			self.fig1.canvas.draw_idle()
	
	def manual_init(self, is_reinit:bool=False):
		pass
		# self.init_zscore_data([self.mdata.zs_rf1, self.mdata.zs_rf2, self.mdata.zs_rf3], ['Fundamental', '2nd Harmonic', '3rd Harmonic'], [self.mdata.freq_rf_GHz, self.mdata.freq_rf_GHz, self.mdata.freq_rf_GHz], "Frequency (GHz)")
		
		# self.ylims1 = get_graph_lims(np.concatenate((self.mdata.rf1, self.mdata.rf2, self.mdata.rf3)), step=10)
		# self.xlims1 = get_graph_lims(self.mdata.freq_rf_GHz, step=0.5)
		
	def calc_mask(self):
		b = self.get_condition('sel_bias_mA')
		p = self.get_condition('sel_power_dBm')
		f = self.get_condition('sel_freq_GHz')
		
		# Filter relevant data
		mask_bias = (self.mdata.requested_Idc_mA == b)
		mask_pwr = (self.mdata.power_rf_dBm == p)
		mask_freq = (self.mdata.freq_rf_GHz == f)
		loc_mask = (mask_bias & mask_pwr & mask_freq)
		
		if self.get_condition(GCOND_REMOVE_OUTLIERS):
			mask = np.array(loc_mask) & np.array(self.mdata.outlier_mask)
			self.log.lowdebug(f"Removing outliers. Mask had {loc_mask.sum()} vals, now {mask.sum()} vals.")
		else:
			self.log.lowdebug(f"Ignoring outlier spec")
			mask = loc_mask
		
		return mask
	
	@updateRenderPB
	def render_plot(self):
		use_fund = self.get_condition(GCOND_FREQXAXIS_ISFUND)
		b = self.get_condition('sel_bias_mA')
		p = self.get_condition('sel_power_dBm')
		f = self.get_condition('sel_freq_GHz')
		
		# Filter relevant data
		mask = self.calc_mask()
			
		# Plot results
		self.ax1.cla()
		
		# Check correct number of points
		mask_len = np.sum(mask)
		if mask_len != 1:
			self.log.debug(f"Cannot complete Spectrum plot. Exactly 1 data point must match (number of matches: {mask_len})")
			self.fig1.canvas.draw_idle()
			return
		
		# if len(self.mdata.unique_freqs) != mask_len:
		# 	log.warning(f"Cannot display data: Mismatched number of points (bias = {b} mA, pwr = {p} dBm, mask: {mask_len}, freq: {len(self.mdata.unique_freqs)})")
		# 	self.fig1.canvas.draw_idle()
		# 	return
		
		self.ax1.plot(np.array(self.mdata.waveform_f_Hz[mask])/1e9, self.mdata.waveform_s_dBm[mask], linestyle=':', marker='o', markersize=4, color=(0, 0.55, 0.75))
		self.ax1.set_xlabel("Frequency (GHz)")
		self.ax1.set_title(f"Bias = {b} mA, p = {p} dBm, f = {f} GHz")
		self.ax1.set_ylabel("Power (dBm)")
		self.ax1.grid(True)
		self.default_xlims = self.ax1.get_xlim()
		
		# if self.get_condition('fix_scale'):
		# 	self.ax1.set_ylim(self.ylims1)
		# 	if use_fund:
		# 		self.ax1.set_xlim(self.xlims1)
		# 	else:
		# 		self.ax1.set_xlim((self.xlims1[0], self.xlims1[1]*3))
		self.fig1.tight_layout()
		
		self.fig1.canvas.draw_idle()
		
		self.plot_is_current = True

class PowerDomainTabWidget(QTabWidget):
	
	def __init__(self, global_conditions:dict, main_window):
		super().__init__()
		
		self.main_window = main_window
		self.object_list = []
		self._is_active = False
		
		#------------ Max Bias widget
		
		self.object_list.append(HarmGenBiasDomainPlotWidget(global_conditions, self.main_window.log, self.main_window.mdata))
		self.main_window.gcond_subscribers.append(self.object_list[-1])
		self.addTab(self.object_list[-1], "Harmonic Generation")
		
		self.currentChanged.connect(self.update_active_tab)
		
	def set_active(self, b:bool):
		self._is_active = b
		self.update_active_tab()
	
	def update_active_tab(self):
		
		# Set all objects to inactive
		for obj in self.object_list:
			obj.set_active(False)
		
		# Set only the active widget to active
		if self._is_active:
			self.object_list[self.currentIndex()].set_active(True)

class BiasDomainTabWidget(QTabWidget):
	
	def __init__(self, global_conditions:dict, main_window):
		super().__init__()
		
		self.main_window = main_window
		self.object_list = []
		self._is_active = False
		
		#------------ Harmonics widget
		
		self.object_list.append(HarmGenBiasDomainPlotWidget(global_conditions, self.main_window.log, self.main_window.mdata))
		self.main_window.gcond_subscribers.append(self.object_list[-1])
		self.addTab(self.object_list[-1], "Harmonic Generation")
		
		#------------ CE widget
		
		self.object_list.append(CE23BiasDomainPlotWidget(global_conditions, self.main_window.log, self.main_window.mdata))
		self.main_window.gcond_subscribers.append(self.object_list[-1])
		self.addTab(self.object_list[-1], "Efficiency")
		
		#------------ Harmonics widget
		
		self.object_list.append(IVPlotWidget(global_conditions, self.main_window.log, self.main_window.mdata))
		self.main_window.gcond_subscribers.append(self.object_list[-1])
		self.addTab(self.object_list[-1], "Bias Current")
		
		self.currentChanged.connect(self.update_active_tab)
		
	def set_active(self, b:bool):
		self._is_active = b
		self.update_active_tab()
	
	def update_active_tab(self):
		
		# Set all objects to inactive
		for obj in self.object_list:
			obj.set_active(False)
		
		# Set only the active widget to active
		if self._is_active:
			self.object_list[self.currentIndex()].set_active(True)

class FrequencyDomainTabWidget(QTabWidget):
	
	def __init__(self, global_conditions:dict, main_window):
		super().__init__()
		
		self._is_active = False
		
		self.gcond = global_conditions
		self.main_window = main_window
		self.object_list = []
		
		#------------ Harmonics widget
		
		self.object_list.append(HarmGenFreqDomainPlotWidget(self.gcond, self.main_window.log, self.main_window.mdata))
		self.main_window.gcond_subscribers.append(self.object_list[-1])
		self.addTab(self.object_list[-1], "Harmonic Generation")
		
		#------------ CE widget
		
		self.object_list.append(CE23FreqDomainPlotWidget(self.gcond, self.main_window.log, self.main_window.mdata))
		self.main_window.gcond_subscribers.append(self.object_list[-1])
		self.addTab(self.object_list[-1], "Efficiency")
		
		self.currentChanged.connect(self.update_active_tab)
	
	def set_active(self, b:bool):
		self._is_active = b
		self.update_active_tab()
	
	def update_active_tab(self):
		
		# Set all objects to inactive
		for obj in self.object_list:
			obj.set_active(False)
		
		# Set only the active widget to active
		if self._is_active:
			self.object_list[self.currentIndex()].set_active(True)
	
class PointInspecterDomainTabWidget(QTabWidget):
	
	def __init__(self, global_conditions:dict, main_window):
		super().__init__()
		
		self._is_active = False
		
		self.gcond = global_conditions
		self.main_window = main_window
		self.object_list = []
		
		#------------ Spectrum widget
		
		self.object_list.append(SpectrumPIDomainPlotWidget(self.gcond, self.main_window.log, self.main_window.mdata))
		self.main_window.gcond_subscribers.append(self.object_list[-1])
		self.addTab(self.object_list[-1], "Spectrum")
		
		self.currentChanged.connect(self.update_active_tab)
	
	def set_active(self, b:bool):
		self._is_active = b
		self.update_active_tab()
	
	def update_active_tab(self):
		
		# Set all objects to inactive
		for obj in self.object_list:
			obj.set_active(False)
		
		# Set only the active widget to active
		if self._is_active:
			self.object_list[self.currentIndex()].set_active(True)


class SPDTabWidget(QTabWidget):
	''' S-Parameter Domain Tab Widget'''
	
	def __init__(self, global_conditions:dict, main_window):
		super().__init__()
		
		self._is_active = False
		
		self.gcond = global_conditions
		self.main_window = main_window
		self.object_list = []
		
		#------------ Harmonics widget
		
		self.object_list.append(SParamSPDPlotWidget(self.gcond, self.main_window.log, self.main_window.mdata))
		self.main_window.gcond_subscribers.append(self.object_list[-1])
		self.addTab(self.object_list[-1], "S-Parameters")
		
		# #------------ CE widget
		
		# self.object_list.append(CE23FreqDomainPlotWidget(global_conditions=self.gcond))
		# self.main_window.gcond_subscribers.append(self.object_list[-1])
		# self.addTab(self.object_list[-1], "Efficiency")
		
		# self.currentChanged.connect(self.update_active_tab)
	
	def set_active(self, b:bool):
		self._is_active = b
		self.update_active_tab()
	
	def update_active_tab(self):
		
		# Set all objects to inactive
		for obj in self.object_list:
			obj.set_active(False)
		
		# Set only the active widget to active
		if self._is_active:
			self.object_list[self.currentIndex()].set_active(True)
	
class HGA1Window(QtWidgets.QMainWindow):

	def __init__(self, log, mdata, app, *args, **kwargs):
		super().__init__(*args, **kwargs)
		
		# Save local variables
		self.log = log
		self.app = app
		self.mdata = mdata
		
		# Initialize global conditions
		self.gcond = {'sel_freq_GHz': self.mdata.unique_freqs[len(self.mdata.unique_freqs)//2], 'sel_power_dBm': self.mdata.unique_pwr[len(self.mdata.unique_pwr)//2], 'sel_bias_mA': self.mdata.unique_bias[len(self.mdata.unique_bias)//2], 'fix_scale':False, GCOND_FREQXAXIS_ISFUND:False, GCOND_BIASXAXIS_ISMEAS:True, "remove_outliers":True, GCOND_OUTLIER_ZSCE2:10, GCOND_OUTLIER_ZSCE3:10, GCOND_OUTLIER_ZSEXTRAZ:None, GCOND_OUTLIER_VALEXTRAZ: None, GCOND_ADJUST_SLIDER:True}
		
		self.gcond_subscribers = []
		
		# Basic setup
		self.setWindowTitle("Harmonic Generation Data Analyzer")
		self.grid = QtWidgets.QGridLayout() # Create the primary layout
		self.add_menu()
		
		# Make a controls widget
		self.control_widget = OutlierControlWidget(self.gcond, self.log, self.mdata, self.plot_all, self.reinit_all, show_frame=True)
		self.dataselect_widget = DataSelectWidget(self.gcond, self.log, self.mdata, self.plot_all, self.dataset_changed, show_frame=True)
		
		# Create tab widget
		self.tab_widget_widgets = []
		self.tab_widget = QtWidgets.QTabWidget()
		self.tab_widget.currentChanged.connect(self.update_active_tab)
		self.make_tabs() # Make tabs
		
		# Make sliders
		self.slider_box = QtWidgets.QWidget()
		self.populate_slider_box()
		
		# Active main sweep file label
		self.active_file_label = QLabel()
		self.active_file_label.setText(f"Active Main Sweep File: {self.mdata.current_sweep_file}")
		self.active_file_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
		
		# Active s-param file label
		self.active_spfile_label = QLabel()
		self.active_spfile_label.setText(f"Active S-Parameter File: {self.mdata.current_sparam_file}")
		self.active_spfile_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
		
		# progress bar
		self.status_bar = StatusBar()
		
		
		# Place each widget
		self.grid.addWidget(self.control_widget, 0, 0)
		self.grid.addWidget(self.tab_widget, 0, 1)
		self.grid.addWidget(self.slider_box, 0, 2)
		self.grid.addWidget(self.dataselect_widget, 1, 0, 1, 3)
		self.grid.addWidget(self.active_file_label, 2, 1, 1, 2)
		self.grid.addWidget(self.active_spfile_label, 3, 1, 1, 2)
		self.grid.addWidget(self.status_bar, 4, 0, 1, 3)
		
		# Set the central widget
		central_widget = QtWidgets.QWidget()
		central_widget.setLayout(self.grid)
		self.setCentralWidget(central_widget)
		
		self.show()
	
	def close(self):
		''' This will be called before the window closes. Save any stuff etc here.'''
		
		pass
	
	def get_condition(self, c:str):
	
		if c in self.gcond:
			return self.gcond[c]
		else:
			return None
	
	def set_gcond(self, key, value):
		
		self.gcond[key] = value
		
		for sub in self.gcond_subscribers:
			sub.gcond[key] = value
	
	def plot_all(self):
		
		for sub in self.gcond_subscribers:
			sub.update_plot()
	
	def plot_active_zscore(self):
		
		for sub in self.gcond_subscribers:
			sub.plot_zscore_if_active()
	
	def save_active_graph(self):
		
		# Scan over subscribers and get figures
		for sub in self.gcond_subscribers:
			active_figs = sub.get_fig_if_active()
			
			if active_figs is not None:
				break
		
		if active_figs is not None:
			
			for afig in active_figs:
				name_tup = QFileDialog.getSaveFileName(self, 'Save File')
				name = name_tup[0]
				
				# Ensure proper extension
				if len(name) < 5 or name[-5:].upper() != ".GRAF":
					name = name + ".graf"
				
				# Create graf
				write_GrAF(afig, name, conditions=self.gcond)
				self.log.info(f"Saved figure to file '{name}'.")
				

	def reinit_all(self):
		
		for sub in self.gcond_subscribers:
			sub.manual_init(is_reinit=True)
	
	def update_freq(self, x):
		try:
			new_freq = self.mdata.unique_freqs[x]
			self.set_gcond('sel_freq_GHz', new_freq)
			self.plot_all()
		except Exception as e:
			log.warning(f"Index out of bounds! ({e})")
			return
		
		self.freq_slider_vallabel.setText(f"{new_freq} GHz")
	
	def update_active_tab(self):
		
		# Set all objects to inactive
		for obj in self.tab_widget_widgets:
			obj.set_active(False)
		
		self.tab_widget_widgets[self.tab_widget.currentIndex()].set_active(True)
	
	def update_pwr(self, x):
		try:
			new_pwr = self.mdata.unique_pwr[x]
			self.set_gcond('sel_power_dBm', new_pwr)
			self.plot_all()
		except Exception as e:
			log.warning(f"Index out of bounds! ({e})")
		
		self.pwr_slider_vallabel.setText(f"{new_pwr} dBm")
		
	def update_bias(self, x):
		try:
			new_b = self.mdata.unique_bias[x]
			self.set_gcond('sel_bias_mA', new_b)
			self.plot_all()
		except Exception as e:
			log.warning(f"Index out of bounds! ({e})")
		
		self.bias_slider_vallabel.setText(f"{new_b} dBm")
	
	def populate_slider_box(self):
		
		ng = QtWidgets.QGridLayout()
		
		self.freq_slider_hdrlabel = QtWidgets.QLabel()
		self.freq_slider_hdrlabel.setText("Frequency\n(GHz)")
		
		self.freq_slider_vallabel = QtWidgets.QLabel()
		self.freq_slider_vallabel.setText("VOID (GHz)")
		
		self.freq_slider = QSlider(Qt.Orientation.Vertical)
		self.freq_slider.valueChanged.connect(self.update_freq)
		self.freq_slider.setSingleStep(1)
		self.freq_slider.setMinimum(0)
		self.freq_slider.setMaximum(len(np.unique(self.mdata.unique_freqs))-1)
		self.freq_slider.setTickInterval(1)
		self.freq_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksLeft)
		self.freq_slider.setSliderPosition(0)
		
		self.pwr_slider_hdrlabel = QtWidgets.QLabel()
		self.pwr_slider_hdrlabel.setText("Power\n(dBm)")
		
		self.pwr_slider_vallabel = QtWidgets.QLabel()
		self.pwr_slider_vallabel.setText("VOID (dBm)")
		
		self.pwr_slider = QSlider(Qt.Orientation.Vertical)
		self.pwr_slider.valueChanged.connect(self.update_pwr)
		self.pwr_slider.setSingleStep(1)
		self.pwr_slider.setMinimum(0)
		self.pwr_slider.setMaximum(len(np.unique(self.mdata.unique_pwr))-1)
		self.pwr_slider.setTickInterval(1)
		self.pwr_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksLeft)
		self.pwr_slider.setSliderPosition(0)
		
		self.bias_slider_hdrlabel = QtWidgets.QLabel()
		self.bias_slider_hdrlabel.setText("Bias\n(mA)")
		
		self.bias_slider_vallabel = QtWidgets.QLabel()
		self.bias_slider_vallabel.setText("VOID (mA)")
		
		self.bias_slider = QSlider(Qt.Orientation.Vertical)
		self.bias_slider.valueChanged.connect(self.update_bias)
		self.bias_slider.setSingleStep(1)
		self.bias_slider.setMinimum(0)
		self.bias_slider.setMaximum(len(self.mdata.unique_bias)-1)
		self.bias_slider.setTickInterval(1)
		self.bias_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksLeft)
		self.bias_slider.setSliderPosition(0)
		
		# bottomBtn = QPushButton(icon=QIcon("./assets/max_ce2.png"), parent=self)
		# bottomBtn.setFixedSize(100, 40)
		# bottomBtn.setIconSize(QSize(100, 40))
		
		self.btn_groupbox = QGroupBox()
		self.btn_groupbox.setFlat(True)
		self.btn_groupbox.setStyleSheet("QGroupBox{border:0;}")
		
		self.maxce2_btn = QPushButton("Max CE2", parent=self)
		self.maxce2_btn.setFixedSize(100, 40)
		self.maxce2_btn.clicked.connect(self._set_max_ce2)
		
		self.maxce3_btn = QPushButton("Max CE3", parent=self)
		self.maxce3_btn.setFixedSize(100, 40)
		self.maxce3_btn.clicked.connect(self._set_max_ce3)
		
		self.btn_groupbox_grid = QGridLayout()
		self.btn_groupbox_grid.addWidget(self.maxce2_btn, 0, 0)
		self.btn_groupbox_grid.addWidget(self.maxce3_btn, 0, 1)
		self.btn_groupbox.setLayout(self.btn_groupbox_grid)
		
		ng.addWidget(self.freq_slider_hdrlabel, 0, 0)
		ng.addWidget(self.freq_slider, 1, 0, alignment=Qt.AlignmentFlag.AlignHCenter)
		ng.addWidget(self.freq_slider_vallabel, 2, 0)
		
		ng.addWidget(self.pwr_slider_hdrlabel, 0, 1)
		ng.addWidget(self.pwr_slider, 1, 1, alignment=Qt.AlignmentFlag.AlignHCenter)
		ng.addWidget(self.pwr_slider_vallabel, 2, 1)
		
		ng.addWidget(self.bias_slider_hdrlabel, 0, 2)
		ng.addWidget(self.bias_slider, 1, 2, alignment=Qt.AlignmentFlag.AlignHCenter)
		ng.addWidget(self.bias_slider_vallabel, 2, 2)
		
		ng.addWidget(self.btn_groupbox, 3, 0, 1, 3)
		
		self.slider_box.setLayout(ng)
		
		# Copy of mdata vals so if mdata is reloaded to a new file, the
		# old values can be read one more time to readjust sliders to appropriate position
		self.slider_unique_bias = copy.deepcopy(self.mdata.unique_bias)
		self.slider_unique_pwr = copy.deepcopy(self.mdata.unique_pwr)
		self.slider_unique_freqs = copy.deepcopy(self.mdata.unique_freqs)
		
		# Trigger all slider callbacks
		self.update_bias(self.bias_slider.value())
		self.update_freq(self.freq_slider.value())
		self.update_pwr(self.pwr_slider.value())
	
	def dataset_changed(self):
		''' Call when the dataset changes. It will readjust the slider positions to something valid for the new dataset.'''
		
		# Get old values to match
		try:
			prev_bias = self.slider_unique_bias[self.bias_slider.value()]
			prev_pwr = self.slider_unique_pwr[self.pwr_slider.value()]
			prev_freq = self.slider_unique_freqs[self.freq_slider.value()]
		except:
			# If this function gets called during init and before any datasets are loaded, just skip it.
			return
		
		# Update slider limits
		self.bias_slider.setMaximum(len(self.mdata.unique_bias)-1)
		self.pwr_slider.setMaximum(len(self.mdata.unique_pwr)-1)
		self.freq_slider.setMaximum(len(self.mdata.unique_freqs)-1)
		
		# Move sliders to closest match positions
		if self.get_condition(GCOND_ADJUST_SLIDER):
			self.bias_slider.setSliderPosition(np.argmin(np.abs(self.mdata.unique_bias - prev_bias)))
			self.freq_slider.setSliderPosition(np.argmin(np.abs(self.mdata.unique_freqs - prev_freq)))
			self.pwr_slider.setSliderPosition(np.argmin(np.abs(self.mdata.unique_pwr - prev_pwr)))
		else:
			self.bias_slider.setSliderPosition(0)
			self.freq_slider.setSliderPosition(0)
			self.pwr_slider.setSliderPosition(0)
		
		# Copy of mdata vals so if mdata is reloaded to a new file, the
		# old values can be read one more time to readjust sliders to appropriate position
		self.slider_unique_bias = copy.deepcopy(self.mdata.unique_bias)
		self.slider_unique_pwr = copy.deepcopy(self.mdata.unique_pwr)
		self.slider_unique_freqs = copy.deepcopy(self.mdata.unique_freqs)
		
		# Trigger all slider callbacks
		self.update_bias(self.bias_slider.value())
		self.update_freq(self.freq_slider.value())
		self.update_pwr(self.pwr_slider.value())
		
		# Reinitialize all widgets (this will fix their autolims and recalculate z-scores)
		for gcs in self.gcond_subscribers:
			gcs.manual_init()
	
	def _set_max_ce2(self):
		
		if self.get_condition(GCOND_REMOVE_OUTLIERS):
			mask = np.array(self.mdata.outlier_mask)
		else:
			mask = np.full(len(self.mdata.ce2), True)
		
		# Find index of max CE2 value
		idx_max = np.argmax(self.mdata.ce2[mask])
		
		# Select power, freq, and bias to match
		bmax = self.mdata.requested_Idc_mA[mask][idx_max]
		pmax = self.mdata.power_rf_dBm[mask][idx_max]
		fmax = self.mdata.freq_rf_GHz[mask][idx_max]
		
		# Find the index of each (on the unique slider scales)
		bmax_idx = np.where(self.mdata.unique_bias == bmax)[0][0]
		pmax_idx = np.where(self.mdata.unique_pwr == pmax)[0][0]
		fmax_idx = np.where(self.mdata.unique_freqs == fmax)[0][0]

		
		# Set slider positions
		self.freq_slider.setSliderPosition((fmax_idx))
		self.pwr_slider.setSliderPosition((pmax_idx))
		self.bias_slider.setSliderPosition((bmax_idx))
	
	def _set_max_ce3(self):
		
		if self.get_condition(GCOND_REMOVE_OUTLIERS):
			mask = np.array(self.mdata.outlier_mask)
		else:
			mask = np.full(len(self.mdata.ce3), True)
		
		# Find index of max CE2 value
		idx_max = np.argmax(self.mdata.ce3[mask])
		
		# Select power, freq, and bias to match
		bmax = self.mdata.requested_Idc_mA[mask][idx_max]
		pmax = self.mdata.power_rf_dBm[mask][idx_max]
		fmax = self.mdata.freq_rf_GHz[mask][idx_max]
		
		# Find the index of each (on the unique slider scales)
		bmax_idx = np.where(self.mdata.unique_bias == bmax)[0][0]
		pmax_idx = np.where(self.mdata.unique_pwr == pmax)[0][0]
		fmax_idx = np.where(self.mdata.unique_freqs == fmax)[0][0]

		
		# Set slider positions
		self.freq_slider.setSliderPosition((fmax_idx))
		self.pwr_slider.setSliderPosition((pmax_idx))
		self.bias_slider.setSliderPosition((bmax_idx))
	
	def make_tabs(self):
		
		self.tab_widget_widgets.append(BiasDomainTabWidget(self.gcond, self))
		self.tab_widget.addTab(self.tab_widget_widgets[-1], "Main Sweep - Bias Domain")
		
		self.tab_widget_widgets.append(FrequencyDomainTabWidget(self.gcond, self))
		self.tab_widget.addTab(self.tab_widget_widgets[-1], "Main Sweep - Frequency Domain")
		
		self.tab_widget_widgets.append(PointInspecterDomainTabWidget(self.gcond, self))
		self.tab_widget.addTab(self.tab_widget_widgets[-1], "Main Sweep - Single Point")
		
		self.tab_widget_widgets.append(SPDTabWidget(self.gcond, self))
		self.tab_widget.addTab(self.tab_widget_widgets[-1], "S-Parameters")
	
	def add_menu(self):
		''' Adds menus to the window'''
		
		self.bar = self.menuBar()
		
		# File Menu --------------------------------------
		
		self.file_menu = self.bar.addMenu("File")
		self.file_menu.triggered[QAction].connect(self._process_file_menu)
		
		self.save_graph_act = QAction("Save Graph", self)
		self.save_graph_act.setShortcut("Ctrl+Shift+G")
		self.file_menu.addAction(self.save_graph_act)
		
		self.close_window_act = QAction("Close Window", self)
		self.close_window_act.setShortcut("Ctrl+W")
		self.file_menu.addAction(self.close_window_act)
		
		# Graph Menu --------------------------------------
		
		self.graph_menu = self.bar.addMenu("Graph")
		self.graph_menu.triggered[QAction].connect(self._process_graph_menu)
		
		self.adjust_sliders_act = QAction("Preserve Sliders", self, checkable=True)
		self.adjust_sliders_act.setShortcut("Ctrl+;")
		self.adjust_sliders_act.setChecked(True)
		self.set_gcond(GCOND_ADJUST_SLIDER, self.adjust_sliders_act.isChecked())
		self.graph_menu.addAction(self.adjust_sliders_act)
		
		self.fix_scales_act = QAction("Fix Scales", self, checkable=True)
		self.fix_scales_act.setShortcut("Ctrl+F")
		self.fix_scales_act.setChecked(True)
		self.set_gcond('fix_scale', self.fix_scales_act.isChecked())
		self.graph_menu.addAction(self.fix_scales_act)
		
		self.legacy_peak_act = QAction("Legacy Peak Detection", self, checkable=True)
		# self.fix_scales_act.setShortcut("Ctrl+Shift+")
		self.legacy_peak_act.setChecked(self.mdata.dlm.use_legacy_peakdetect)
		self.graph_menu.addAction(self.legacy_peak_act)
		
			# Graph Menu: Freq-axis sub menu -------------
		
		self.freqxaxis_graph_menu = self.graph_menu.addMenu("Frequency X-Axis")
		
		self.freqxaxis_group = QActionGroup(self)
		
		self.freqxaxis_fund_act = QAction("Show Fundamental", self, checkable=True)
		self.freqxaxis_harm_act = QAction("Show Harmonics", self, checkable=True)
		self.freqxaxis_harm_act.setChecked(True)
		self.freqxaxis_harm_act.setShortcut("Shift+X")
		self.freqxaxis_fund_act.setShortcut("Ctrl+Shift+X")
		self.set_gcond(GCOND_FREQXAXIS_ISFUND, self.freqxaxis_fund_act.isChecked())
		self.freqxaxis_graph_menu.addAction(self.freqxaxis_fund_act)
		self.freqxaxis_graph_menu.addAction(self.freqxaxis_harm_act)
		self.freqxaxis_group.addAction(self.freqxaxis_fund_act)
		self.freqxaxis_group.addAction(self.freqxaxis_harm_act)
		
			# Graph Menu: Bias-axis sub menu -------------
		
		
		
		self.biasxaxis_graph_menu = self.graph_menu.addMenu("Bias X-Axis")
		
		self.biasxaxis_group = QActionGroup(self)
		
		self.biasxaxis_req_act = QAction("Show Requested", self, checkable=True)
		self.biasxaxis_meas_act = QAction("Show Measured", self, checkable=True)
		self.biasxaxis_meas_act.setChecked(True)
		self.biasxaxis_req_act.setShortcut("Shift+B")
		self.biasxaxis_meas_act.setShortcut("Ctrl+Shift+B")
		self.set_gcond(GCOND_BIASXAXIS_ISMEAS, self.biasxaxis_meas_act.isChecked())
		self.biasxaxis_graph_menu.addAction(self.biasxaxis_req_act)
		self.biasxaxis_graph_menu.addAction(self.biasxaxis_meas_act)
		self.biasxaxis_group.addAction(self.biasxaxis_req_act)
		self.biasxaxis_group.addAction(self.biasxaxis_meas_act)
		
			# END Graph Menu: Bias-axis sub menu -------------
		
		self.zscore_act = QAction("Show Active Z-Score", self)
		self.zscore_act.setShortcut("Shift+Z")
		self.graph_menu.addAction(self.zscore_act)
		
		# S-Parameter Menu --------------------------------------
		
		self.sparam_menu = self.bar.addMenu("S-Params")
		self.sparam_menu.triggered[QAction].connect(self._process_sparam_menu)
		
		self.sparam_showsum_act = QAction("Show Sum", self, checkable=True)
		self.sparam_showsum_act.setShortcut("Shift+S")
		self.sparam_showsum_act.setChecked(False)
		self.set_gcond('sparam_show_sum', self.sparam_showsum_act.isChecked())
		self.sparam_menu.addAction(self.sparam_showsum_act)
		
	def _process_file_menu(self, q):
		
		if q.text() == "Save Graph":
			
			self.save_active_graph()
			
		if q.text() == "Close Window":
			self.close()
			sys.exit(0)
	
	def _process_graph_menu(self, q):
		
		if q.text() == "Fix Scales":
			self.set_gcond('fix_scale', self.fix_scales_act.isChecked())
			self.plot_all()
		elif q.text() == "Preserve Sliders":
			self.set_gcond(GCOND_ADJUST_SLIDER, self.adjust_sliders_act.isChecked())
			self.plot_all()
		elif q.text() == "Show Fundamental" or q.text() == "Show Harmonics":
			self.set_gcond(GCOND_FREQXAXIS_ISFUND, self.freqxaxis_fund_act.isChecked())
			self.plot_all()
		elif q.text() == "Show Requested" or q.text() == "Show Measured":
			self.set_gcond(GCOND_BIASXAXIS_ISMEAS, self.biasxaxis_meas_act.isChecked())
			self.plot_all()
		elif q.text() == "Show Active Z-Score":
			self.plot_active_zscore()
		elif q.text() == "Legacy Peak Detection":
			self.mdata.dlm.use_legacy_peakdetect = self.legacy_peak_act.isChecked()
			self.mdata.dlm.clear_data()
			self.dataselect_widget.reload_sweep()
	
	def _process_sparam_menu(self, q):
		
		if q.text() == "Show Sum":
			self.set_gcond('sparam_show_sum', self.sparam_showsum_act.isChecked())
			self.plot_all()

dlm = DataLoadingManager(log, conf_file=os.path.join(".", "hga_conf.json"))
master_data = MasterData(log, dlm)
app = QtWidgets.QApplication(sys.argv)
app.setStyle(f"Fusion")
app.setWindowIcon(QIcon("./assets/icon.png"))

chicago_ff = get_font("./assets/Chicago.ttf")
menlo_ff = get_font("./assets/Menlo-Regular.ttf")
if cli_args.theme:
	app.setStyleSheet(f"""
	QWidget {{
		font-family: '{chicago_ff}';
	}}""")
else:
	app.setStyleSheet(f"""
	QWidget {{
		font-family: '{menlo_ff}';
	}}""")

if platform == "win32":
	# Manually override app ID to tell windows to use the Window Icon in the taskbar
	myappid = 'giesbrecht.hga.main.v0' # arbitrary string
	ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

w = HGA1Window(log, master_data, app)
w.mdata.add_main_window(w)

app.exec()

#TODO: When bias is set to show requested, the fixed scale doesnt work. Look at max-CE2 in 8Aug dataset.
#TODO: When you turn off the filter, it loads the wrong types of datasets and crashes!