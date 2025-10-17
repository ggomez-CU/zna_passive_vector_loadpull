import matplotlib.pyplot as plt
import numpy as np
from classes import *
from pylogfile.base import *
from tqdm import tqdm
from datetime import datetime
import shutil
import matplotlib.pyplot  as plt
import os
from scipy.io import loadmat

def ab2gamma(T,R,directivity,tracking,port_match):
    # eq from hackborn. extrapolated equation 
    return directivity + (tracking*T/R)/(1-port_match*T/R)

if __name__ == "__main__":
    config = SystemValidationPowerConfig(r"C:\Users\grgo8200\Documents\AFRL_Testbench\data\systemvalidation\systemvalidation_power_config.json")
    now = datetime.now().strftime("%Y-%m-%d_%H_%M")
    output_dir = os.getcwd() + "\\data\\systemvalidation\\" \
            + now + "_Freq" \
            + str(config.frequency[0]) + "to" + str(config.frequency[-1])
    os.mkdir(output_dir)

    #Estimate Time and ensure test should be run.
    config_file = output_dir + "\\config_file.json"
    config_data = output_file_test_config_data(config_file, config, now)
    # print(" ==========\tTEST CONFIGURATION\t========== ")
    # print(json.dumps(config_data, indent=4))
    # print('\n\n')
    # expected_test_time(config)
    # print(f"Estimated Pout of the PreAmp: {[float(x)+30 for x in config.input_power_dBm]}")
    # print(f"Estimated Pin Power Meter: {[float(x)+24 for x in config.input_power_dBm]}")
    # input("Press Enter to continue...")   

    # Initialize instruments
    loadtuner = MY982AU(config.loadtuner_config.port, config.loadtuner_config.sn)
    loadtuner.connect()
    if not loadtuner.connected:
        exit()
    loadtuner.set_cal(config.loadtuner_config.calfile)
    loadtuner.set_freq(str(float(config.frequency[0])*1e9))
    loadtuner.checkError
    pm = HP_E4419B("GPIB1::13::INSTR")
    pm.inst.timeout = 10000
    pna = Agilent_PNA_E8300("GPIB1::16::INSTR")
    pna.set_freq_start((float(config.frequency[0])*1e9))
    pna.set_freq_end((float(config.frequency[0])*1e9))	
    pna.write("SENS:SWE:POIN 1")
    pna.init_loadpull()
    pna.set_power(-27)

    columns = ('Power (dB/dBm)')
    rows = ['Output Error','Input Erro','Measured Coupled','Coupling','Expected PM','Measured PM','Compensation']
 
    # input("Press Enter to continue...")

    fig = plt.figure(constrained_layout=True)

    for freq in config.frequency:

        plt.close(fig) 
        fig = plt.figure(constrained_layout=True)
        axs = fig.subplot_mosaic([['Power','OutputIL','Coupling'],[ 'Gamma','MeasTable', 'MeasTable']],
                            per_subplot_kw={"Gamma": {"projection": "polar"}})
        axs['Power'].set_title('Power')
        axs['Gamma'].set_title('Gamma')
        axs['OutputIL'].set_title('Output Insertion Loss')
        axs['Coupling'].set_title('Output Coupling')
        axs['MeasTable'].set_title('Power Values')
        axs['Gamma'].grid(True)
        line1, = axs['Gamma'].plot([], [], marker='o', ms=1, linewidth=0)
        line_in, = axs['Power'].plot([min(config.input_power_dBm), max(config.input_power_dBm)],[20, -30], marker='o', ms=4, linewidth=0,label='Input')
        line_out, = axs['Power'].plot([min(config.input_power_dBm), max(config.input_power_dBm)],[20, -30], marker='o', ms=4, linewidth=0,label='Output')
        line_pm, = axs['Power'].plot([min(config.input_power_dBm), max(config.input_power_dBm)],[20, -30], marker='o', ms=4, linewidth=0,label='Power Meter')
        axs['Power'].legend()
        axs['Coupling'].plot(config.freqs_IL,config.output_coupling, linewidth=3)
        axs['OutputIL'].plot(config.freqs_IL,config.output_IL, linewidth=3)

        output_file = output_dir + f"\\{now}_{freq}GHz.json"
        pna.set_freq_start((float(freq)*1e9))
        pna.set_freq_end((float(freq)*1e9))	
        pm.set_freq((float(freq)*1e9))	
        loadtuner.set_freq(str(float(freq)*1e9))
        loadtuner.checkError

        error_terms = config.get_error_terms_freq(freq)

        fig.suptitle(f'Power Characterization for {freq} GHz', fontsize=16)
        output_power_plot = np.array([])
        input_power_plot = np.array([])
        set_power_plot = np.array([])
        gammaload_plot = np.array([]).astype(complex)
        meas_power_plot = np.array([])
        line1.set_data([np.angle(gammaload_plot)], [np.abs(gammaload_plot)])

        with open(output_file, 'w') as f:
            json.dump(config_data, f, indent = 4)
        data = config_data

        for power in tqdm(config.input_power_dBm):

            pna.set_power(power)
            for i in range(5):
                if not loadtuner.connected:
                    print("There is an error")
                    exit()

                # time.sleep(1)
                gammaload = ab2gamma(pna.get_trace_data_raw(3), pna.get_trace_data_raw(4), 
                error_terms['match'], error_terms['tracking'], error_terms['directivity'])[0]

                if i == 1:
                    time.sleep(1)
                    meas_power = pm.get_power()
                    pm.write("INIT:CONT")
                else:
                    meas_power = pm.fetch_power()
                wave_temp = pna.get_loadpull_data()
                datatemp = {'PNA Power: '+ str(power) + str(i): 
                            {'wave data': wave_temp,
                            'Gamma Load': {'real': gammaload.real,
                                'imag': gammaload.imag},
                            'Power Meter': meas_power,
                            }
                        } 
                data.update(datatemp)

                # print(json.dumps(datatemp, indent=4))

                with open('temp.json', 'w') as f:
                    json.dump(data,f,indent=4)

                os.remove(output_file)
                shutil.copyfile('temp.json', output_file)

                gammaload_plot = np.append(gammaload_plot,complex(gammaload.real,gammaload.imag))
                output_power_plot = np.append(output_power_plot,wave_temp['output_bwave']['dBm_mag'][0])
                input_power_plot = np.append(input_power_plot,wave_temp['input_awave']['dBm_mag'][0])
                set_power_plot = np.append(set_power_plot,power)
                meas_power_plot = np.append(meas_power_plot,meas_power)
                line_in.set_data(set_power_plot,input_power_plot)
                line_out.set_data(set_power_plot,output_power_plot)
                line_pm.set_data(set_power_plot,meas_power_plot)
                line1.set_data([np.angle(gammaload_plot)], [np.abs(gammaload_plot)])
                axs['MeasTable'].cla()
                axs['MeasTable'].axis('off')
                axs['MeasTable'].table(cellText=[[meas_power - (wave_temp['output_bwave']['dBm_mag'][0]+config.get_comp_freq(freq)['output coupling'])],
                        [meas_power - (wave_temp['input_awave']['dBm_mag'][0]+config.get_comp_freq(freq)['input coupling'])],
                        [wave_temp['output_bwave']['dBm_mag'][0]],
                        [config.get_comp_freq(freq)['output coupling']],
                        [wave_temp['output_bwave']['dBm_mag'][0]+config.get_comp_freq(freq)['output coupling']],
                        [meas_power],
                        [config.get_comp_freq(freq)['output IL']]],
                      rowLabels=rows,
                      colLabels=columns,
                      loc='center')
                
                plt.pause(0.25)
                fig.canvas.draw()
                fig.canvas.flush_events()
                # input("Press Enter to continue...")
pna.set_power(-27)
pna.close()
loadtuner.close()
pm.close()