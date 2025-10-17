import numpy as np
import pyvisa

class InstrumentClass():

    def __init__(self, port, channel = None, ConnectionType = 'GPIB1'):
        self.connected = False
        self.port = str(port)
        self.ConnectionType = ConnectionType
        self.IDN = ""
        self.instr = None

        if channel:
            channel = str(channel)

        self.channel = channel

        #Run functions
        self.InstrumentConnection()

    def InstrumentConnection(self):
        rm = pyvisa.ResourceManager()
        #rm.list_resources()

        print('Attempting connection to port ' + self.port +'... ', end='')
        try:
            self.instr = rm.open_resource(self.ConnectionType + '::' + self.port + '::INSTR')
        except:
            print('connection unsuccessful')
            return

        self.IDN = self.instr.query("*IDN?").rstrip()
        print('Instrument Identified as ' + self.IDN + "...", end='')
        print('connection successful\n')
        self.connected = 1
