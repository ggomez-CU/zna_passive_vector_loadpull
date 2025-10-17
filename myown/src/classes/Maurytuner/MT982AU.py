import socket
import numpy as np
 
class MY982AU():

    def __init__(self, port:int, tuner_res:str='3002', driver:str='MauryMicrowave_Legacy, FTD2XX'):
        # MTune 3 Telnet connection (input telnet IP and socket)
        self.instr = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.instr.connect((r'localhost', port))
        self.tuner_res = tuner_res
        self.driver = driver
        self.connected = False
        self.position = ''
 
    def checkError(self):
        init_count = self.query("SYSTEM:ERROR:COUNT?")
        while self.query("SYSTEM:ERROR:COUNT?") != '0':
            print(self.query("SYSTEM:ERROR?"))
        if init_count != '0': 
            print(f"error count was {init_count}")   
            return True

    def write(self, dataIn):
        self.instr.sendall(str.encode(dataIn + '\n'))
    
    def query(self, dataIn):
        self.instr.sendall(str.encode(dataIn + '\n'))
        return self.instr.recv(2147483647).decode().rstrip('\n')
    
    def set_cal(self, calfile):
        self.write("PORT:LOAD:TUNER1:CHAR:FILE " + calfile )

    def connect(self):

        self.write('SYSTEM:TERMINAL OFF')
        self.write('SYSTem:ERRor:CLEar')
        print("Setting Up Tuner")

        self.write(f"PORT:SOURCE:CLEAR")
        self.write(f"PORT:LOAD:CLEAR")
        self.write(f"PORT:LOAD:ENABLED TRUE")
        self.write(f"PORT:LOAD:TUNER:ADD")

        #comm protocol
        self.write(f"PORT:LOAD:TUNER1:DRIVER {self.driver}")
        self.write(f"PORT:LOAD:TUNER1:RESOURCE {self.tuner_res}")

        # Connect and initialize all tuners
        self.write(f"PORT:LOAD:CONNECT")
        print("Initializing Tuner...")
        self.write(f"PORT:LOAD:INITIALIZE")
        self.query(f"*OPC?")

        error = self.checkError()
        if error:
            self.connected = False
            print(f"Could not connect to tuner.")
        else:
            self.connected = True
 
    def init_tuner(self):
        self.write(f"PORT:LOAD:INITIALIZE")
        self.query(f"*OPC?")

        error = self.checkError()
        if error:
            self.connected = False
            print(f"Could not connect to tuner.")
        else:
            self.connected = True

    def set_freq(self, freq):
        try:
            self.write("PORT:LOAD:FREQUENCY:CLEAR")
            self.write(f"PORT:LOAD:FREQUENCY:ADD {freq}")

            self.freq = freq
        except self.checkError() as e:
            print(f"Could not connect to tuner. Exception: {e}")

    def get_moving_bin(self):
        position = self.get_position()
        # print(f"{position} {self.position}")
        if self.position == position:
            return False
        else:
            self.position = position
            return True

    def wait_for_ready(self):
        while self.get_moving_bin():
            pass
        while self.query("*OPC?") != '1':
            print(f"occupied {self.query("*OPC?")}")

    def set_gamma_complex(self, gamma:complex):
        if self.freq is not None:
            if not self.checkError():
                self.write(f"PORT:LOAD:TUNE {str(np.abs(gamma))} {str(np.angle(gamma)/np.pi*180)}")
                self.wait_for_ready()
        else:
            print("No frequency defined or Error")
                
    def get_position(self):
        return self.query("PORT:LOAD:TUNE:POS?")
        
    def close(self):
        self.instr.close()
        self.connected = False

    def set_gamma_MagPhs(self, gamma_mag:float, gamma_phase_deg:float):
        if self.freq is not None:
            if not self.checkError():
                self.write(f"PORT:LOAD:TUNE {str(gamma_mag)} {str(gamma_phase_deg)}")
                self.wait_for_ready()
        else:
            print("No frequency defined")

 
