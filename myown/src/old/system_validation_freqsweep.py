import matplotlib.pyplot as plt
import numpy as np
from classes import *
from pylogfile.base import *
from tqdm import tqdm
from datetime import datetime
import shutil
import matplotlib.pyplot  as plt
import os

if __name__ == "__main__":

    config = SystemValidationFreqConfig(r"C:\Users\grgo8200\Documents\GitHub\summer2025_loadpull_repo\\data\systemvalidation\systemvalidation_freq_config.json")
    now = datetime.now().strftime("%Y-%m-%d_%H_%M")
    output_dir = os.getcwd() + "\\data\\systemvalidation\\loadgain" \
            + now + "_Freq" \
            + str(config.frequency[0]) + "to" + str(config.frequency[-1])
    os.mkdir(output_dir)

    # Initialize instruments and log pile
    loadtuner = MY982AU(config.loadtuner_config.port, config.loadtuner_config.sn)
    loadtuner.connect()
    if not loadtuner.connected:
        exit()
    loadtuner.set_cal(config.loadtuner_config.calfile)
    loadtuner.set_freq(str(float(config.frequency[0])*1e9))
    loadtuner.checkError()

    plt.ion() 

    pna = Agilent_PNA_E8300("GPIB1::16::INSTR")
    pna.set_freq_start((float(config.frequency[0])*1e9))
    pna.set_freq_end((float(config.frequency[0])*1e9))	
    pna.write("SENS:SWE:POIN 1")
    pna.init_loadpull()

    config_file = output_dir + "\\config_file.json"
    config_data = output_file_test_config_data(config_file, config, now)

    for freq in config.frequency:

        output_file = output_dir + f"\\{now}_{freq}GHz.json"
        pna.set_freq_start((float(freq)*1e9))
        pna.set_freq_end((float(freq)*1e9))	
        loadtuner.set_freq(str(float(freq)*1e9))
        loadtuner.checkError

        with open(output_file, 'w') as f:
            json.dump(config_data, f, indent = 4)
        data = config_data
        try:
            os.remove('temp.json')
        except:
            pass

        
        for i in range(1):
            if not loadtuner.connected:
                print("There is an error")
                exit()
            loadtuner.set_gamma_complex(complex(0,0))
            s11 = pna.get_trace_data_raw(5)[0]

            datatemp = {'Load Point: '+ str(complex(0,0)) + '_' + str(i): 
                        {'load_gamma': 
                            {'real': 0,
                            'imag': 0},
                        'wave data': pna.get_loadpull_data(),
                        'Input Power': pna.get_power(),
                        "s11":
                            {'real': s11.real,
                            'imag': s11.imag},
                        }
                    } 
            data.update(datatemp)

            # print(json.dumps(datatemp, indent=4))

            with open('temp.json', 'w') as f:
                json.dump(data,f,indent=4)

            os.remove(output_file)
            shutil.copyfile('temp.json', output_file)

        for loadpoint in tqdm(config.loadpoints):

            for i in range(1):
                if not loadtuner.connected:
                    print("There is an error")
                    exit()
                loadtuner.set_gamma_complex(loadpoint)
                s11 = pna.get_trace_data_raw(5)[0]

                datatemp = {'Load Point: '+ str(loadpoint) + '_' + str(i): 
                            {'load_gamma': 
                                {'real': loadpoint.real,
                                'imag': loadpoint.imag},
                            'wave data': pna.get_loadpull_data(),
                            'Input Power': pna.get_power(),
                            "s11":
                                {'real': s11.real,
                                'imag': s11.imag},
                            }
                        } 
                data.update(datatemp)

                # print(json.dumps(datatemp, indent=4))

                with open('temp.json', 'w') as f:
                    json.dump(data,f,indent=4)

                os.remove(output_file)
                shutil.copyfile('temp.json', output_file)
                
pna.close()
loadtuner.close()