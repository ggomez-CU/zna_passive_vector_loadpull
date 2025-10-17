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
import sys
from optparse import OptionParser
import io
import math
import traceback


def updateplot(axs, line, data, coupling, idx, plots):
    keys_list = list(data.keys())

    columns = ('Power (dB/dBm)')
    rows = ['DUT Input (dBm)','DUT Output (dBm)','Gain','Pin','Sampler 1','Sampler 2']

    outputdBm =  round(data[keys_list[0]]['wave data']['output_bwave']['dBm_mag'][0]+coupling['output coupling'],3)
    inputdBm = round(data[keys_list[0]]['wave data']['input_awave']['dBm_mag'][0]+coupling['input coupling'],3)
    plots['set_power'] = np.append(plots['set_power'],inputdBm)
    plots['sampler1'] = np.append(plots['sampler1'],data[keys_list[0]]['Samplers']['1'])
    plots['sampler2'] = np.append(plots['sampler2'],data[keys_list[0]]['Samplers']['2'])

    load = complex(data[keys_list[0]]['load_gamma']['real'],data[keys_list[0]]['load_gamma']['imag'])

    plots['gammaload'] = np.append(plots['gammaload'],load)

    line[0][0].set_data([np.angle(plots['gammaload'])], [np.abs(plots['gammaload'])])
    line[2*idx+1][0].set_data(plots['set_power'],plots['sampler1'])
    line[2*idx+2][0].set_data(plots['set_power'],plots['sampler2'])
    axs['MeasTable'].cla()
    axs['MeasTable'].axis('off')
    axs['MeasTable'].table(cellText=[[inputdBm],
            [outputdBm],
            [outputdBm-inputdBm],
            [round(data[keys_list[0]]['Input Power'],3)],
            [round(data[keys_list[0]]['Samplers']['1'],3)],
            [round(data[keys_list[0]]['Samplers']['2'],3)]],
            rowLabels=rows,
            colLabels=columns,
            loc='center')
    return plots

def main(config, options, visa_instrs):

    now = datetime.now().strftime("%Y-%m-%d_%H_%M")
    upper_output_dir = os.getcwd() + "\\data\\coupledline_samplers\\LoadPullBiasing" \
            + now + "_Freq" \
            + str(config.frequency[0]) + "to" + str(config.frequency[-1])
    os.mkdir(upper_output_dir)

    if not options.informal:
        paragraph_lines = []
        print("Enter your Comments. Press Enter on an empty line to finish:")
        while True:
            line = input()
            if not line:  # Check if the line is empty
                break
            paragraph_lines.append(line)

        paragraph = "\n".join(paragraph_lines)
    else:
        paragraph = "None"

    config_file = upper_output_dir + "\\config_file.json"
    config_data = output_file_test_config_data(config_file, config, now, paragraph)
    
    if not (options.override): 
        print(" ==========\tTEST CONFIGURATION\t========== ")
        print(json.dumps(config_data, indent=4))
        print('\n\n')
        if config.specifyDUTinput:
            print(f"Estimated Pout of the PreAmp: {[float(x) for x in config.set_power_dBm]}")
        else:
            print(f"Estimated Pout of the PreAmp: {[float(x)+30 for x in config.set_power_dBm]}")  
        expected_test_time(config)

    if options.quiet:
        text_trap = io.StringIO()
        sys.stdout = text_trap

    fig = plt.figure(constrained_layout=True)

    for idx, bias in enumerate(config.gatebiasvoltage):
        visa_instrs.pna.power_off()
        visa_instrs.dc_supply.set_channel(config.dc_supply_config.gate_channel,bias,0.1) #channel voltage current
        dc_init = {"Initial DC Parameters":
                get_PA_dc(visa_instrs.dc_supply, 
                                                    config.dc_supply_config.gate_channel, 
                                                    config.dc_supply_config.drain_channel) 
            }

        visa_instrs.pna.power_on()
        config_bias = config_data
        lower_output_dir = upper_output_dir + f'\\samplerbias_{bias}V'
        # lower_output_dir = upper_output_dir + f'\\draincurrent_{round(dc_init["Initial DC Parameters"]["drain current"]*1000,3)}mA'
        os.mkdir(lower_output_dir)
        if options.plot:
            plt.close(fig) 
            fig = plt.figure(constrained_layout=True)
            axs = fig.subplot_mosaic([['Samplers','Samplers','Gamma'],[ 'MeasTable','MeasTable', 'MeasTable']],
                                per_subplot_kw={"Gamma": {"projection": "polar"}})
            axs['Gamma'].set_title('Gamma')
            axs['Samplers'].set_title('Samplers')
            axs['MeasTable'].set_title('Power Values')
            axs['Gamma'].grid(True)
            line = []
            line.append(axs['Gamma'].plot([], [], marker='o', ms=1, linewidth=0))
            fig.suptitle(f'PA Drive Up', fontsize=16)
            plots = {}

        for idx, freq in enumerate(config.frequency):
            visa_instrs.pna.set_freq_start((float(freq)*1e9))
            visa_instrs.pna.set_freq_end((float(freq)*1e9))	
            visa_instrs.pm.set_freq((float(freq)*1e9))	
            visa_instrs.loadtuner.set_freq(str(float(freq)*1e9))
            visa_instrs.loadtuner.checkError()

            #file generation
            output_file = lower_output_dir + f"\\{now}_{freq}GHz_{round(dc_init["Initial DC Parameters"]["drain current"]*1000,3)}mA.json"

            with open(output_file, 'w') as f:
                json.dump(config_bias, f, indent = 4)
            data = config_bias

            #Get calibration coefficients (power and sparameters)
            error_terms = config.get_error_terms_freq(freq)
            coupling = config.get_comp_freq(freq)

            if options.plot:
                line.append(axs['Samplers'].plot([min(config.set_power_dBm), max(config.set_power_dBm)],[0, .50], marker='o', ms=4, linewidth=0,label='Sampler 1'))
                line.append(axs['Samplers'].plot([min(config.set_power_dBm), max(config.set_power_dBm)],[0, .5], marker='o', ms=4, linewidth=0,label='Sampler 2'))
                
                # axs['Frequency'].legend()
                # axs['Power'].legend()
                plots.update({'set_power': np.array([])})
                plots.update({'gammaload': np.array([])})
                plots.update({'sampler1': np.array([])})
                plots.update({'sampler2': np.array([])})

            string = str(round(freq,3)) + " GHz"
            time.sleep(2)

            continue_power = True
            for power in tqdm(config.set_power_dBm, ascii=True, desc=string):
                visa_instrs.loadtuner.set_gamma_complex(complex(0,0))
                if config.specifyDUTinput:
                    set_Pin(visa_instrs.pna, coupling, power)
                elif config.specifyDUToutput:
                    set_Pout(visa_instrs.pna, coupling, power)
                else:
                    visa_instrs.pna.set_power(power)

                if options.plot:
                    plots.update({'gammaload': np.array([])})

                for loadpoint in config.loadpoints:

                    visa_instrs.loadtuner.set_gamma_complex(loadpoint)
                    for i in range(1):
                        if not visa_instrs.loadtuner.connected:
                            print("There is an error")
                            exit()
                        time.sleep(2)
                        s11 = visa_instrs.pna.get_trace_data_raw(5)[0]

                        try:
                            rf_data = visa_instrs.pna.get_loadpull_data()
                            dc_data = get_PA_dc(visa_instrs.dc_supply, 
                                                            config.dc_supply_config.gate_channel, 
                                                            config.dc_supply_config.drain_channel)             
                            datatemp = {'Load Point: '+ str(power) + '_' + str(loadpoint) + '_' + str(i): 
                                        {'load_gamma': 
                                            {'real': loadpoint.real,
                                            'imag': loadpoint.imag},
                                        'wave data': rf_data,
                                        'Power Meter': visa_instrs.pm.get_power(),
                                        'Input Power': visa_instrs.pna.get_power(),
                                        'Samplers':{
                                            '1': visa_instrs.dmm1.fetch_voltage(),
                                            '2': visa_instrs.dmm2.fetch_voltage(),
                                            'Bias': visa_instrs.dc_supply.get_voltage(config.dc_supply_config.sampler_channel),
                                            'Bias Current': visa_instrs.dc_supply.get_current(config.dc_supply_config.sampler_channel)
                                            },
                                        'DC Parameters':dc_data,
                                        "s11":
                                        {'real': s11.real,
                                        'imag': s11.imag}
                                        }}
                            visa_instrs.pm.write("INIT:CONT")
                            data.update(datatemp)
                            with open('temp.json', 'w') as f:
                                json.dump(data,f,indent=4)

                            os.remove(output_file)
                            shutil.copyfile('temp.json', output_file)

                            if options.plot:
                                plots = updateplot(axs, line, datatemp, coupling, (idx), plots)
                                plt.pause(0.25)
                                fig.canvas.draw()
                                fig.canvas.flush_events()

                        except Exception as e:
                            print(f"Failed to collect data: {e}")
                

if __name__ == "__main__":
    print("Program started. Press Ctrl+C to exit gracefully.")
    parser = OptionParser(
            description="Specifies User outputs and test validation on or off"
        )
    parser.add_option("-p", "--plot",
                  action="store_true", dest="plot", default=False,
                  help="plot output data while running tests")
    parser.add_option("-v", "--vulnerable",
                  action="store_true", dest="vulnerable", default=False,
                  help="will not run clean shutdown if system fails to execute correctly")
    parser.add_option("-o", "--override",
                  action="store_true", dest="override", default=False,
                  help="Run without checking valid config")
    parser.add_option("-q", "--quiet",
                  action="store_true", dest="quiet", default=False,
                  help="Run without checking valid config")
    parser.add_option("-i", "--informal",
                  action="store_true", dest="informal", default=False,
                  help="No comment from user when initiated. Makes understanding the data harder later")
    parser.add_option("-f", "--file", dest="filename",
                  help="configuration file", metavar="FILE")
    (options, args) = parser.parse_args()


    if options.filename:
        print(f"The specified configuration filename is: {options.filename}")
    else:
        print("No configuration filename was provided.")
        exit()

    print(f"This test will run as quiet {options.quiet} overriden {options.override} and plotted {options.plot}")
    config = MMICDriveUpBiasConfig(options.filename)
    #r"C:\Users\grgo8200\Documents\GitHub\summer2025_loadpull_repo\data\PA_Spring2023\MMIC_driveupbias_loadpull_config.json"
    visa_instrs = VisaInstrsClass(config)

    try:
        main(config, options, visa_instrs)
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt caught. Shutting down gracefully...")
    except Exception as e:
        print(f"Failed to execute: {e}")
        traceback.print_exc() 
    finally:
        if options.vulnerable:
            print("Clean shutdown omitted")
        else:
            print("Performing cleanup operations...")
            visa_instrs.simple_clean_shutdown()  
            print("Cleanup complete. Exiting program.")
        sys.exit(0) # Exit with status code 0 (success)