import matplotlib.pyplot as plt
import numpy as np
from classes import *
from pylogfile.base import *
from tqdm import tqdm
from datetime import datetime
import shutil
import matplotlib.pyplot  as plt
import os

def ab2gamma(T,R,directivity,tracking,port_match):
    # eq from hackborn. extrapolated equation 
    return directivity + (tracking*T/R)/(1-port_match*T/R)

if __name__ == "__main__":

    config = SystemValidationConfig(r"C:\Users\grgo8200\Documents\AFRL_Testbench\data\systemvalidation\systemvalidation_config.json")
    now = datetime.now().strftime("%Y-%m-%d_%H_%M")
    output_file = os.getcwd() + "\\data\\systemvalidation\\" \
            + now + "_Freq" \
            + str(config.frequency[0]) \
            + ".json"
    data = output_file_test_config_data(output_file, config, now)

    #Estimate Time and ensure test should be run.
    # print(" ==========\tTEST CO
    


    # Initialize instruments and log pile
    loadtuner = MY982AU(config.loadtuner_config.port, config.loadtuner_config.sn)
    loadtuner.connect()
    if not loadtuner.connected:
        exit()
    loadtuner.set_cal(config.loadtuner_config.calfile)
    loadtuner.set_freq(str(float(config.frequency[0])*1e9))
    loadtuner.checkError

    plt.ion() 

    pna = Agilent_PNA_E8300("GPIB1::16::INSTR")
    pna.set_freq_start((float(config.frequency[0])*1e9))
    pna.set_freq_end((float(config.frequency[0])*1e9))	
    pna.write("SENS:SWE:POIN 1")
    pna.init_loadpull()

    directivityfile = np.genfromtxt("./data/errordata/20250707/ErrorTerm_22_EDir.csv",  
    delimiter=" ")
    error_freq = np.array(directivityfile[:,0])
    index = int(np.where(error_freq == float(config.frequency[0])*1e9)[0][0])
    print(f"Index {index} freq is {float(config.frequency[0])*1e9}")
        
    if not index:
        print(f"The value was not found in the list.")
        exit()

    directivityfile = np.genfromtxt("./data/errordata/20250707/ErrorTerm_22_EDir.csv", 
    delimiter=" ")
    directivity = np.array([complex(float(directivityfile[index,1]), float(directivityfile[index,2]))])
    trackingfile = np.genfromtxt("./data/errordata/20250707/ErrorTerm_22_ERft.csv", 
    delimiter=" ")
    tracking = np.array([complex(float(trackingfile[index,1]), float(trackingfile[index,2]))])
    port_matchfile = np.genfromtxt("./data/errordata/20250707/ErrorTerm_22_ESrm.csv", 
    delimiter=" ")
    port_match = np.array([complex(float(port_matchfile[index,1]), float(port_matchfile[index,2]))])

    print(f"Error terms are {directivity} {tracking} {port_match}")

    # Set up the polar plot
    fig, ax = plt.subplots(subplot_kw={'projection': 'polar'})
    ax.grid(True)
    ax.set_title("Polar Plot of S11 and Gamma", va='bottom')

    # Initial dummy plots (must unpack the line from plot())
    line1, = ax.plot([], [], marker='o', ms=3, linewidth=0,label='Gamma')
    line2, = ax.plot([], [], marker='o', ms=2, linewidth=0,label='S11')
    line3, = ax.plot([], [], marker='o', ms=1, linewidth=0,label='Load Point')
    ax.legend()

    # Interactive update loop

    # Test specific configuration of test equipment  
    input("Press Enter to continue...")

    s11_plot = np.array([]).astype(complex)
    gammaload_plot = np.array([]).astype(complex)
    loadpoint_plot = np.array([]).astype(complex)

    for loadpoint in tqdm(config.loadpoints):

        for i in range(5):
            if not loadtuner.connected:
                print("There is an error")
                exit()
            loadtuner.set_gamma_complex(loadpoint-config.offset_complex)

            time.sleep(1)
            pna.write("INIT:CONT OFF")
            s11 = pna.get_trace_data_raw(5)[0]
            T = pna.get_trace_data_raw(3)
            R = pna.get_trace_data_raw(4)
            gammaload = ab2gamma(T, R, port_match, tracking, directivity)[0]
            pna.write("INIT:CONT ON")

            datatemp = {'Load Point: '+ str(loadpoint) + '_' + str(i): 
                        {'load_gamma': 
                            {'real': loadpoint.real,
                            'imag': loadpoint.imag},
                            'PNA S11':
                            {'real': s11.real,
                            'imag': s11.imag},
                            'PNA Gamma Load': {'real': gammaload.real,
                            'imag': gammaload.imag},
                        }
                    } 
            data.update(datatemp)

            # print(json.dumps(datatemp, indent=4))

            with open('temp.json', 'w') as f:
                json.dump(data,f,indent=4)

            os.remove(output_file)
            shutil.copyfile('temp.json', output_file)

            s11_plot = np.append(s11_plot,complex(s11.real,s11.imag))
            gammaload_plot = np.append(gammaload_plot,complex(gammaload.real,gammaload.imag))
            laodpoint_plot = np.append(loadpoint_plot,complex(loadpoint.real,loadpoint.imag))

            line2.set_data([np.angle(s11_plot)], [np.abs(s11_plot)])
            line1.set_data([np.angle(gammaload_plot)], [np.abs(gammaload_plot)])
            line3.set_data([np.angle(loadpoint_plot)], [np.abs(loadpoint_plot)])
            plt.pause(0.25)
            fig.canvas.draw()
            fig.canvas.flush_events()
            # input("Press Enter to continue...")

pna.close()
loadtuner.close()