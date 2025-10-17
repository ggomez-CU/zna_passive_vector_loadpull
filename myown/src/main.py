from visaClass import *
from configClass import *
from testloop import *

import sys
from optparse import OptionParser
import traceback

if __name__ == "__main__":
    print("Program started. Press Ctrl+C to exit gracefully.")

# region Options Parser
    parser = OptionParser(
            description="Specifies User outputs and test validation on or off"
        )
    parser.add_option("-p", "--plot",
                  action="store_true", dest="plot", default=False,
                  help="plot output data while running tests")
    parser.add_option("-v", "--vulnerable",
                  action="store_true", dest="vulnerable", default=False,
                  help="Run without shutdowning gracefully if system fails to execute correctly")
    parser.add_option("-o", "--override",
                  action="store_true", dest="override", default=False,
                  help="Run without checking valid config")
    parser.add_option("-q", "--quiet",
                  action="store_true", dest="quiet", default=False,
                  help="Run without outputs")
    parser.add_option("-i", "--informal",
                  action="store_true", dest="informal", default=False,
                  help="No comment from user when initiated. Makes understanding the data harder later")
    parser.add_option("-f", "--file", dest="filename",
                  help="configuration file", metavar="FILE")
    (options, args) = parser.parse_args()

    if options.filename:
        print(f"The specified configuration filename is: {options.filename}")
        config = configClass(options.filename)
        testparams = testparamsClass()
    else:
        print("No configuration filename was provided.")
        exit()

    if not options.informal:
        testparams.getComment()
    
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

    if options.plot:
        plots = plotClass(config)

# endregion Options Parser
    visa_instrs = visaClass(config)


    try:
        testloop(config, options, visa_instrs)
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt caught. Shutting down gracefully...")
        visa_instrs.simple_clean_shutdown()  
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