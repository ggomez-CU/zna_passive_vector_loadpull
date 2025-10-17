import numpy as np
import time

def get_percent_error_DUTout(loadZ:complex, power_meter_dBm, output_comped_dBm):
    # returns a percentage
    gamma = (loadZ-50)/(loadZ+50)
    expected = power_meter_dBm + 20*np.log10(abs(gamma))
    return abs(output_comped_dBm - expected)/output_comped_dBm*100

def get_Pin_comp(rf, coupling, input_desired):
    return (input_desired-(rf['input_awave']['dBm_mag'][0]+coupling['input coupling']))

def set_Pin(pna, coupling, input_desired, tolerance=0.1, max_limit_pna=2, min_limit_pna=-27):
    rf = pna.get_loadpull_data()
    error = get_Pin_comp(rf, coupling, input_desired)
    current_power = pna.get_power()
    # print(f"\nSetting power to {input_desired},", end="")
    while(abs(error) > tolerance):
        if (current_power + error) > max_limit_pna:
            print(f"Attempted power exceeds specified limit of {max_limit_pna}: dBm")
            return 1
        if (current_power + error) < min_limit_pna:
            print(f"Attempted power less than minimum specified limit of {min_limit_pna}: dBm")
            return 1
        pna.set_power(float(current_power + error))
        time.sleep(0.5)
        current_power = pna.get_power()
        # print(f"{current_power},", end="")
        rf = pna.get_loadpull_data()
        error = get_Pin_comp(rf, coupling, input_desired)
    return 0

    
def get_Pout_comp(rf, coupling, output_desired, estimated_gain):
    return (output_desired-estimated_gain-(rf['input_awave']['dBm_mag'][0]+coupling['input coupling']))

def set_Pout(pna, coupling, output_desired, tolerance=0.1, max_limit_pna=2, min_limit_pna=-27):
    rf = pna.get_loadpull_data()
    current_power = pna.get_power()
    PA_gain = get_PA_gain(rf, coupling)
    error = get_Pout_comp(rf, coupling, output_desired, PA_gain['Gain'])
    while(abs(error) > tolerance):
        if (current_power + error) > max_limit_pna:
            print(f"Attempted power exceeds specified limit of {max_limit_pna}: dBm")
            return 1
        if (current_power + error) < min_limit_pna:
            print(f"Attempted power less than minimum specified limit of {min_limit_pna}: dBm")
            return 1
        pna.set_power(float(current_power + error))
        time.sleep(0.5)
        current_power = pna.get_power()
        rf = pna.get_loadpull_data()
        PA_gain = get_PA_gain(rf, coupling)
        error = get_Pout_comp(rf, coupling, output_desired, PA_gain['Gain'])
    return 0

def get_PA_dc(dc_supply, gate_channel, drain_channel):
    return {'gate current': dc_supply.get_current(gate_channel),
    'gate voltage': dc_supply.get_voltage(gate_channel),
    'drain current': dc_supply.get_current(drain_channel),
    'drain voltage': dc_supply.get_voltage(drain_channel)}

def get_PA_gain(rf:dict, coupling:dict):
    rf_input = rf['input_awave']['dBm_mag'][0]+coupling['input coupling']
    rf_output = rf['output_bwave']['dBm_mag'][0]+coupling['output coupling']
    return {'Gain': rf_output-rf_input}

def get_PA_metrics(dc:dict, rf:dict, coupling:dict):
    rf_input = rf['input_awave']['dBm_mag'][0]+coupling['input coupling']
    rf_output = rf['output_bwave']['dBm_mag'][0]+coupling['output coupling']
    Pdc = dc['gate current']*dc['gate voltage']+ dc['drain current']*dc['drain voltage']
    return {'Gain': rf_output-rf_input,
            'PAE': .1*(10**(rf_output/10)-10**(rf_input/10))/Pdc,
            'DC Power': Pdc}