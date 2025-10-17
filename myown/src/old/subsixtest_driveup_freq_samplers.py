"""
Created on 4/2/2025

Simple Loadpull Sub6 Testbench

@author: Grace Gomez

This is a python script for running a single power and single frequency (simple) load pull on the CU Boulder RFPAL ZVA Sub 6 GHz test bench 

"""


"""
Created on 4/2/2025

Simple Loadpull Sub6 Testbench

@author: Grace Gomez

This is a python script for running a single power and single frequency (simple) load pull on the CU Boulder RFPAL ZVA Sub 6 GHz test bench 

"""
from classes import *

from focustuner.Tuner import Tuner
from pylogfile.base import *
from tqdm import tqdm
from datetime import datetime
import shutil
import osa

if __name__ == "__main__":

    # config_filename = find_config_file()
    log = LogPile()
    config = DriveupConfig(r"C:\Users\grgo8200\LocalOnly\DiscreteIS\SubSixTestHybridBoard\subsixtest\data\driveup\driveup_config_hyrbidlumped_freq.json", log)
    now = datetime.now().strftime("%Y-%m-%d_%H_%M")
    output_dir = os.getcwd() + "\\data\\driveup\\" \
            + now + "_Freq" \
            + str(config.frequency[0]) + "to" + str(config.frequency[-1])\
            + "_Pow" + str(config.input_power_dBm[0]) + "to" + str(config.input_power_dBm[-1])
    os.mkdir(output_dir)

    config_file = output_dir + "\\config_file.json"
    config_data = output_file_test_config_data(config_file, config, now)

    #Estimate Time and ensure test should be run.
    print(" ==========\tTEST CONFIGURATION\t========== ")
    print(json.dumps(config_data, indent=4))
    print('\n\n')
    expected_test_time(config)

    #Initialize instruments and log pile
    loadtuner = Tuner(config.loadtuner_config.IP_address, 
                          config.loadtuner_config.timeout , 
                          config.loadtuner_config.port, 
                          config.loadtuner_config.printstatements)
    loadtuner.connect()
    loadtuner.configure()
    # position_cal = LoadTunerCalCalc(rf"C:\Users\grgo8200\LocalOnly\DiscreteIS\SubSixTestHybridBoard\subsixtest\data\LTfreqSparam\3000MHz.txt",
    #                                 loadtuner.configuration.axis_limits[0], 
    #                                 loadtuner.configuration.axis_limits[1], 
    #                                 loadtuner.configuration.step_size)
    zva = RohdeSchwarzZVA("TCPIP0::10.0.0.10::INSTR", log)
    zva.init_zva_subsix_loadpull(config.ZVA_config)

    sampler_1 = MultimeterClass(11, ConnectionType = 'GPIB0')
    sampler_2 = MultimeterClass(13, ConnectionType = 'GPIB0')
    mixer = MultimeterClass(23, ConnectionType = 'GPIB0')

    # Test specific configuration of test equipment  

    for freq in config.frequency:
        zva.set_freq_cw(float(freq)*10**9)
        output_file = output_dir + f"\\{now}_{freq}GHz.json"
        try:
            if freq > 3.8: 
                y_axis_idx = 2
                y_axis = 'y_high'
            else: 
                y_axis_idx = 1
                y_axis = 'y_low'
            position_cal = LoadTunerCalCalc(rf"C:\Users\grgo8200\LocalOnly\DiscreteIS\SubSixTestHybridBoard\subsixtest\data\LTfreqSparam\{int(freq*1000)}MHz.txt",
                                    loadtuner.configuration.axis_limits[0], 
                                    loadtuner.configuration.axis_limits[y_axis_idx], 
                                    loadtuner.configuration.step_size)
        except Exception as e:
            print(e)
            zva.set_power(-60)
            quit()
        # loadtuner.move(y_axis, position_cal.linear_gamma_pos(abs(0)))

        with open(output_file, 'w') as f:
            json.dump(config_data, f, indent = 4)
        data = config_data

        for power in tqdm(config.input_power_dBm):
            zva.set_power(power)
            # settle
            time.sleep(3)
            datatemp = {'ZVA Power: '+ str(power): 
                {'wave_data': zva.get_loadpull_data(),
                'DC voltages': {
                    'Sampler 1': sampler_1.measure_dc(),
                    'Sampler 2': sampler_2.measure_dc(),
                    'Mixer': mixer.measure_dc()}}
                } 

            data.update(datatemp)

            with open('temp.json', 'w') as f:
                json.dump(data,f,indent=4)

            os.remove(output_file)
            shutil.copyfile('temp.json', output_file)

            # input("Press Enter to continue...")

zva.set_power(-60)
zva.close()
loadtuner.close()

sampler_1.close()
sampler_2.close()
mixer.close()