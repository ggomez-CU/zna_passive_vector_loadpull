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

def ab2gamma(T,R,directivity,tracking,port_match):
    # eq from hackborn. extrapolated equation 
    return directivity + (tracking*T/R)/(1-port_match*T/R)

def updateplot(axs, line, data,coupling):
    keys_list = list(data.keys())

    plots['set_power_plot'] = np.append(plots['set_power_plot'],data[keys_list[0]]['Input Power'])

    outputdBm =  round(data[keys_list[0]]['wave data']['output_bwave']['dBm_mag'][0]+coupling['output coupling'],3)
    inputdBm = round(data[keys_list[0]]['wave data']['input_awave']['dBm_mag'][0]+coupling['input coupling'],3)
    plots['output_power_plot'] = np.append(plots['output_power_plot'],outputdBm)
    plots['input_power_plot'] = np.append(plots['input_power_plot'],inputdBm)
    plots['output_error_plot'] = np.append(plots['output_error_plot'],(data[keys_list[0]]['Power Meter'] - outputdBm))
    plots['input_error_plot'] = np.append(plots['input_error_plot'],(data[keys_list[0]]['Power Meter'] - inputdBm))

    gammaload = ab2gamma(complex(data[keys_list[0]]['wave data']['output_awave']['y_real'][0], data[keys_list[0]]['wave data']['output_awave']['y_imag'][0]),
            complex(data[keys_list[0]]['wave data']['output_bwave']['y_real'][0], data[keys_list[0]]['wave data']['output_bwave']['y_imag'][0]),
                                error_terms['match'], error_terms['tracking'], error_terms['directivity'])

    plots['gammaload_plot'] = np.append(plots['gammaload_plot'],gammaload)

    line[0][0].set_data([np.angle(plots['gammaload_plot'])], [np.abs(plots['gammaload_plot'])])
    line[1][0].set_data(plots['set_power_plot'],plots['output_power_plot'])
    line[2][0].set_data(plots['set_power_plot'],plots['input_power_plot'])
    line[3][0].set_data(plots['set_power_plot'],np.subtract(plots['output_power_plot'],plots['input_power_plot']))
    line[4][0].set_data(plots['set_power_plot'],plots['output_error_plot'])
    line[5][0].set_data(plots['set_power_plot'],plots['input_error_plot'])
    axs['MeasTable'].cla()
    axs['MeasTable'].axis('off')
    axs['MeasTable'].table(cellText=[[inputdBm],
            [outputdBm],
            [outputdBm-inputdBm],
            [data[keys_list[0]]['Power Meter'] - outputdBm],
            [data[keys_list[0]]['Power Meter'] - inputdBm],
            [data[keys_list[0]]['Input Power']]],
            rowLabels=rows,
            colLabels=columns,
            loc='center')

if __name__ == "__main__":

    parser = OptionParser(
        description="Specifies User outputs and test validation on or off"
    )
    parser.add_option("-p", "--plot",
                  action="store_true", dest="plot", default=False,
                  help="plot output data while running tests")
    parser.add_option("-f", "--force",
                  action="store_true", dest="force", default=False,
                  help="Run without checking valid config")
    parser.add_option("-v", action="store_true", dest="verbose", default=True)
    parser.add_option("-q", action="store_false", dest="verbose",
                  help="don't print status messages to stdout")
    parser.add_option("-i", "--informal",
                  action="store_true", dest="informal", default=False,
                  help="no comment from user when initiated. Makes understanding the data harder later")
    (options, args) = parser.parse_args()

    print(f"This test will run as quiet {options.verbose} forced {options.force} and plotted {options.plot}")

    config = SystemValidationPowerConfig(r"C:\Users\grgo8200\Documents\GitHub\summer2025_loadpull_repo\data\systemvalidation\systemvalidation_power_config.json")
    now = datetime.now().strftime("%Y-%m-%d_%H_%M")
    output_dir = os.getcwd() + "\\data\\systemvalidation\\" \
            + now + "_Freq" \
            + str(config.frequency[0]) + "to" + str(config.frequency[-1])
    os.mkdir(output_dir)

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


#region Optional Configuration User Validation
    #Estimate Time and ensure test should be run.
    config_file = output_dir + "\\config_file.json"
    config_data = output_file_test_config_data(config_file, config, now, paragraph)
    
    if not (options.force): 
        print(" ==========\tTEST CONFIGURATION\t========== ")
        print(json.dumps(config_data, indent=4))
        print('\n\n')
        expected_test_time(config)
        print(f"Estimated Pout of the PreAmp: {[float(x)+30 for x in config.input_power_dBm]}")
        print(f"Estimated Pin Power Meter: {[float(x)+24 for x in config.input_power_dBm]}")
        input("Press Enter to continue...")   
#end region

#region Initialize Instruments
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
#end region

    columns = ('Power (dB/dBm)')
    rows = ['DUT Input (dBm)','DUT Output (dBm)','Gain','Output Error','Input Error','Pin']
    if not (options.force): 
        input("Press Enter to continue...")

    if options.verbose:
        text_trap = io.StringIO()
        sys.stdout = text_trap

    fig = plt.figure(constrained_layout=True)

    for freq in config.frequency:

        if options.plot:
            plt.close(fig) 
            fig = plt.figure(constrained_layout=True)
            axs = fig.subplot_mosaic([['Power','Error','Gain'],[ 'Gamma','MeasTable', 'MeasTable']],
                                per_subplot_kw={"Gamma": {"projection": "polar"}})
            axs['Power'].set_title('Power')
            axs['Gamma'].set_title('Gamma')
            axs['Error'].set_title('Error')
            axs['Gain'].set_title('Gain')
            axs['MeasTable'].set_title('Power Values')
            axs['Gamma'].grid(True)
            line = []
            line.append(axs['Gamma'].plot([], [], marker='o', ms=1, linewidth=0))
            line.append(axs['Power'].plot([min(config.input_power_dBm), max(config.input_power_dBm)],[20, -30], marker='o', ms=4, linewidth=0,label='Input'))
            line.append(axs['Power'].plot([min(config.input_power_dBm), max(config.input_power_dBm)],[20, -30], marker='o', ms=4, linewidth=0,label='Output'))
            axs['Power'].legend()
            line.append(axs['Gain'].plot([min(config.input_power_dBm), max(config.input_power_dBm)],[.1, -.1], marker='o', ms=4, linewidth=0,label='Gain Thru'))
            line.append(axs['Error'].plot([min(config.input_power_dBm), max(config.input_power_dBm)],[.1, -.1], marker='o', ms=4, linewidth=0,label='Output'))
            line.append(axs['Error'].plot([min(config.input_power_dBm), max(config.input_power_dBm)],[.1, -.1], marker='o', ms=4, linewidth=0,label='Input'))
            axs['Error'].legend()
            fig.suptitle(f'Power Characterization for {freq} GHz', fontsize=16)
            plots = {}
            plots.update({'output_power_plot': np.array([])})
            plots.update({'output_error_plot': np.array([])})
            plots.update({'input_error_plot': np.array([])})
            plots.update({'input_power_plot': np.array([])})
            plots.update({'set_power_plot': np.array([])})
            plots.update({'gammaload_plot': np.array([])})
            # plots.update({'meas_power_plot': np.array([])})
            line[0][0].set_data([np.angle(plots['gammaload_plot'])], [np.abs(plots['gammaload_plot'])])

#region Set Instrumentation and Data to Frequency
        pna.set_freq_start((float(freq)*1e9))
        pna.set_freq_end((float(freq)*1e9))	
        pm.set_freq((float(freq)*1e9))	
        loadtuner.set_freq(str(float(freq)*1e9))
        loadtuner.checkError

        #file generation
        output_file = output_dir + f"\\{now}_{freq}GHz.json"
        with open(output_file, 'w') as f:
            json.dump(config_data, f, indent = 4)
        data = config_data

        #Get calibration coefficients (power and sparameters)
        error_terms = config.get_error_terms_freq(freq)
        coupling = config.get_comp_freq(freq)
        
#endregion
        string = str(round(freq,3)) + " GHz"
        for power in tqdm(config.input_power_dBm, ascii=True, desc=string):
#region Set input power
            pna.set_power(power)
#endregion
            for i in range(5):
                if not loadtuner.connected:
                    print("There is an error")
                    exit()

                # input("press enter...")

                if i == 0:
                    time.sleep(1)
                    datatemp = {'PNA Power: '+ str(power) + str(i): 
                                {'wave data': pna.get_loadpull_data(),
                                'Power Meter': pm.get_power(),
                                'Input Power': power                                    }
                                }
                    pm.write("INIT:CONT")
                else:
                    datatemp = {'PNA Power: '+ str(power) + str(i): 
                                {'wave data': pna.get_loadpull_data(),
                                'Power Meter': pm.fetch_power(), 
                                'Input Power': power                                 }
                                }
                data.update(datatemp)

                with open('temp.json', 'w') as f:
                    json.dump(data,f,indent=4)

                os.remove(output_file)
                shutil.copyfile('temp.json', output_file)

                if options.plot:
                    updateplot(axs, line, datatemp,coupling)
                    # print(plots)
                    # input("press enter...")
                    plt.pause(0.25)
                    fig.canvas.draw()
                    fig.canvas.flush_events()
pna.set_power(-27)
pna.close()
loadtuner.close()
pm.close()