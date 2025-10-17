import os
import json

def expected_test_time(config):

    time_estimate = 0.75

    try: time_estimate = time_estimate*len(config.frequency)
    except: pass

    try: time_estimate = time_estimate*len(config.input_power_dBm)
    except: pass
    
    try: time_estimate = time_estimate*len(config.loadpoints)
    except: pass

    print("\n\n\t##########\t Program Initialization \t##########\t\n")
    print("This program is estimated to take " + str(time_estimate) + " minutes.\nWARNING: This is a simple first order estimate and accuracy is not guaranteed.\nDo you want to continue?\n")
    user_input = input("(Y/N): ")
    if user_input.lower() == 'N'.lower():
        exit()
    elif user_input.lower() == 'Y'.lower():
        print("Continuing.")
        pass
    else:
        print("Unknown Input. Terminating program")
        exit()

def find_config_file():
    # Look for config file for test setup. Reauired for all tests.
    config_filename = None; # Can be edited here in code. If not it will be requested when code is run.

    while config_filename == None:
        print("\n\nPlease input the location (including full filepath) and name (.json) of the test configuration file:")
        config_filename = input()
        config_filename = os.path.abspath(config_filename)
        if (config_filename.endswith('.json') 
                    and os.path.exists(config_filename) ):
            print("Using file " + str(config_filename) + " for configuration\n")
            pass   
        else:
            print("Config file: "+ str(config_filename) + " is unusable. Please include full filepath. Example: " + r'C:\Users\[Username]]\Documents\simpleloadpull_config1.json' + "\n")
            config_filename = None
    
    return os.path.abspath(config_filename)

def output_file_test_config_data(output_file, config_file, now, comments='None'):

    data = ({"Date and Time": now})
    data.update({"Comments": comments})
    data.update({"Configuration": config_file.config_file_json})

    with open(output_file, 'w') as f:
        json.dump(data, f, indent = 4)
        return data