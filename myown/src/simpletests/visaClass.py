import numpy as np
import pyvisa
import time
from classes import *

class VisaInstrsClass():

    def __init__(self, config):
        self.open = True
        self.config = config
        self.pna = self.init_pna()
        self.loadtuner = self.init_loadtuner()
        self.pm = self.init_pm()
        self.dmm1 = self.init_dmm(1)
        self.dmm2 = self.init_dmm(2)
        self.dmm3 = self.init_dmm(3)
        self.dc_supply = self.init_dc_supply()

    def init_pna(self):
        try:
            pna = Agilent_PNA_E8300("GPIB1::16::INSTR")
            pna.set_freq_start((float(self.config.frequency[0])*1e9))
            pna.set_freq_end((float(self.config.frequency[0])*1e9))	
            pna.write("SENS:SWE:POIN 1")
            pna.init_loadpull()
            pna.set_power(-27)
        except Exception as e:
            print(f"PNA not connected. An error occurred: {e}")
            pna = None
        return pna

    def init_pm(self):
        try:
            pm = HP_E4419B("GPIB1::13::INSTR")
            pm.inst.timeout = 10000
        except Exception as e:
            print(f"Power Meter not connected. An error occurred: {e}")
            pm = None
        return pm

    def init_loadtuner(self):
        try:
            loadtuner = MY982AU(self.config.loadtuner_config.port, self.config.loadtuner_config.sn)
            loadtuner.connect()
            loadtuner.set_cal(self.config.loadtuner_config.calfile)
            loadtuner.set_freq(str(float(self.config.frequency[0])*1e9))
            loadtuner.checkError
        except Exception as e:
            print(f"Load tuner not connected. An error occurred: {e}")
            loadtuner = None
        return loadtuner

    def init_dmm(self, num):
        try:
            dmm = Keysight_34400(self.config.sampler_config[num-1].address)
            dmm.set_measurement("voltage-dc")
        except Exception as e:
            print(f"Digital Multimeter not connected. An error occurred: {e}")
            dmm = None
        return dmm

    def init_dc_supply(self):
        try:
            dc_supply = Keithly_2230(self.config.dc_supply_config.address)
        except Exception as e:
            print(f"Load tuner not connected. An error occurred: {e}")
            dc_supply = None
        return dc_supply

    def clean_shutdown(self):
        self.clean = True
        try:
            self.pna.power_off()
        except:
            self.clean = False
            try:
                print("Could not turn off pna power. Attempting to minimize power. Device damaged minimized but not mitigated")
                self.pna.set_power(-27)
            except Exception as e:
                print("Fatal Error. Unable to turn off RF. Cannot cleanly terminate program")
                print(e)

        try:
            print("Pinching off device")
            time.sleep(5)
            self.dc_supply.set_channel(self.config.dc_supply_config.gate_channel,5,0.01) #channel voltage current
            time.sleep(5)
            print("Turning off device")
            self.dc_supply.set_channel(self.config.dc_supply_config.drain_channel,0,0.1)
        except Exception as e:
            print("Could not turn off device. Possible fatal error.")
            print(e)
            self.clean = False

        try:
            rm = pyvisa.ResourceManager()
            rm.close()
            print("All VISA connections closed.")
        except Exception as e:
            print("Could not close connections")
            self.clean = False

    def simple_clean_shutdown(self):
        self.clean = True
        try:
            self.pna.power_off()
        except:
            self.clean = False
            try:
                print("Could not turn off pna power. Attempting to minimize power. Device damaged minimized but not mitigated")
                self.pna.set_power(-27)
            except Exception as e:
                print("Fatal Error. Unable to turn off RF. Cannot cleanly terminate program")
                print(e)

    
        try:
            rm = pyvisa.ResourceManager()
            rm.close()
            print("All VISA connections closed.")
        except Exception as e:
            print("Could not close connections")
            self.clean = False