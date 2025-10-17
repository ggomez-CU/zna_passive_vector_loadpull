"""
Created on 4/2/2025

Simple Loadpull Sub6 Testbench

@author: Grace Gomez

This is a python script for running a single power and single frequency (simple) load pull on the CU Boulder RFPAL ZVA Sub 6 GHz test bench 

"""
from classes import *

from pylogfile.base import *
from tqdm import tqdm
from datetime import datetime
import shutil
import os

if __name__ == "__main__":

    log = LogPile()
    config = SimpleLoadpullConfig(r"C:\Users\grgo8200\LocalOnly\DiscreteIS\SubSixTestHybridBoard\subsixtest\data\simpleloadpull\simpleloadpull_config_hyrbidlumped.json", log)
    now = datetime.now().strftime("%Y-%m-%d_%H_%M")
    output_file = os.getcwd() + "\\data\\simpleloadpull\\" \
            + now + "_Freq" \
            + str(config.frequency[0]) \
            + "_Pow" + str(config.input_power_dBm[0]) \
            + ".json"
    data = output_file_test_config_data(output_file, config, now)

    #Estimate Time and ensure test should be run.
    print(" ==========\tTEST CONFIGURATION\t========== ")
    print(json.dumps(data, indent=4))
    print('\n\n')
    expected_test_time(config)

    #Initialize instruments and log pile
    loadtuner = Tuner(config.loadtuner_config.IP_address, 
                          config.loadtuner_config.timeout , 
                          config.loadtuner_config.port, 
                          config.loadtuner_config.printstatements)
    loadtuner.connect()
    loadtuner.configure()
    if config.frequency[0] > 3.8: 
        y_axis_idx = 2
        y_axis = 'y_high'
    else: 
        y_axis_idx = 1
        y_axis = 'y_low'
    position_cal = LoadTunerCalCalc(rf"C:\Users\grgo8200\LocalOnly\DiscreteIS\SubSixTestHybridBoard\subsixtest\data\LTfreqSparam\{int(freq*1000)}MHz.txt",
                            loadtuner.configuration.axis_limits[0], 
                            loadtuner.configuration.axis_limits[y_axis], 
                            loadtuner.configuration.step_size)
    zva = RohdeSchwarzZVA("TCPIP0::10.0.0.10::INSTR", log)
    zva.init_zva_subsix_loadpull(config.ZVA_config)

    # Initialize samplers
    sampler_1 = MultimeterClass(11, ConnectionType = 'GPIB0')
    sampler_2 = MultimeterClass(13, ConnectionType = 'GPIB0')
    mixer = MultimeterClass(23, ConnectionType = 'GPIB0')

    # Test specific configuration of test equipment  
    zva.set_freq_cw(float(config.frequency[0])*10**9)
    loadtuner.move(y_axis, position_cal.linear_gamma_pos(abs(0)))

    zva.set_power(config.input_power_dBm[0])

    # input("Press Enter to continue...")

    for loadpoint in tqdm(config.loadpoints):
        # loadtuner.move_Z(loadpoint)
        x = position_cal.linear_phi_pos(np.angle(loadpoint)/np.pi*180)
        y = position_cal.linear_gamma_pos(abs(loadpoint))

        if y > loadtuner.configuration.axis_limits[1]:
            y = loadtuner.configuration.axis_limits[1]
            
        print(loadpoint, x, y, np.angle(loadpoint)/np.pi*180, abs(loadpoint))
        loadtuner.move('x', x)
        loadtuner.move(y_axis, y)

        time.sleep(.1)
        datatemp = {'Load Point: '+ str(loadpoint): 
                    {'load_gamma_mag': y,
                    'load_gamma_phi': x, 
                    'wave_data': zva.get_loadpull_data(),
                    'Sampler 1': sampler_1.measure_dc(),
                    'Sampler 2': sampler_2.measure_dc(),
                    'Mixer': mixer.measure_dc()}
            } 
        data.update(datatemp)

        print(json.dumps(datatemp, indent=4))

        with open('temp.json', 'w') as f:
            json.dump(data,f,indent=4)

        os.remove(output_file)
        shutil.copyfile('temp.json', output_file)

        # input("Press Enter to continue...")

zva.set_power(-60)
zva.close()
loadtuner.close()




    


