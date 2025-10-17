class testparamsClass()

    def __init__():
    
    def getComment():
        paragraph_lines = []
        print("Enter your Comments. Press Enter on an empty line to finish:")
        while True:
            line = input()
            if not line:  # Check if the line is empty
                break
            paragraph_lines.append(line)

        self.paragraph = "\n".join(paragraph_lines)

def testloop(config, testparams, visa_instrs):

    plots = testparams.plots

    savedata = saveClass(config)

    for idx, samplerbias in enumerate(config.samplerbiasvoltage):
        for idx, drainbias in enumerate(config.drainbiasvoltage):
            for idx, gatebias in enumerate(config.gatebiaslist):

                if config.gatebiastype == 'Voltage':
                elif config.gatebiastype == 'Current':
                    visa_instrs.vna.power_off()
                    setDrainCurrent()

                dc_init = {"Initial DC Parameters":
                    getDC(visa_instrs.dc_supply,config)}

                savedata.mksubfolder()

        visa_instrs.pna.power_on()
        config_bias = config_data
        lower_output_dir = upper_output_dir + f'\\samplerbias_{bias}V'
        # lower_output_dir = upper_output_dir + f'\\draincurrent_{round(dc_init["Initial DC Parameters"]["drain current"]*1000,3)}mA'
        os.mkdir(lower_output_dir)


























        visa_instrs.pna.power_off()
        visa_instrs.dc_supply.set_channel(config.dc_supply_config.gate_channel,bias,0.1) #channel voltage current


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
                    for i in range(5):
                        if not visa_instrs.loadtuner.connected:
                            print("There is an error")
                            exit()
                        time.sleep(.5)

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
                                        'DC Parameters':dc_data
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
                