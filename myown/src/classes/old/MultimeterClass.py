from .InstrumentClass import *

class MultimeterClass(InstrumentClass):
    
    def __init__(self, port, channel = None, ConnectionType = 'GPIB1', samples = 3):
        InstrumentClass.__init__(self, port, channel, ConnectionType)
        self.samples = samples

    def measure_dc(self, QueryType = "VOLT"):
        dc_meaurement_data = []
        for i in range(self.samples):
            dc_meaurement_data.append(float(self.instr.query(f"MEAS:{QueryType}:DC?").replace("\n", "")))
        return dc_meaurement_data
