import socket
import time

# establish local connection with MTune on port 5025
mTune = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
mTune.connect(("localhost", 5030))
tuner_res = '3002'

def write(dataIn):
    mTune.sendall(str.encode(dataIn + '\n'))

def query(dataIn):
    mTune.sendall(str.encode(dataIn + '\n'))
    return mTune.recv(2147483647).decode().rstrip('\n')

def checkError():
    while query("SYSTEM:ERROR:COUNT?") != '0':
        print(query("SYSTEM:ERROR?"))

# Ensure terminal mode is off
write("SYSTEM:TERMINAL OFF")
checkError()

# #region VNA Measurements
# # NOTE: This is not required for setup.
# # VNA Measurements are performed internally during tuner characterization.

# #region Tuner Characterization
write("PORT:LOAD:CLEAR")
write("PORT:LOAD:ENABLED TRUE")
write("PORT:LOAD:TUNER:ADD")
write(f"PORT:LOAD:TUNER1:DRIVER MauryMicrowave_Legacy, FTD2XX")
write(f"PORT:LOAD:TUNER1:RESOURCE {tuner_res}")

dir = r"C:\Users\grgo8200\Documents\AFRL_Testbench\data\tunercal\MT982AU06_3002.tunx"
checkError()
write("PORT:LOAD:TUNER1:CHAR:FILE " + dir ) #double check

write("PORT:LOAD:FREQUENCY:ADD 8e9")
#Need clear tuner before init new freq
print(query("PORT:LOAD:TUNer1:CHARacterization:SETUP:FREQ:LIST?"))
# Connect and initialize all tuners
write("PORT:LOAD:CONNECT")
write("PORT:LOAD:INITIALIZE")
print(query("*OPC?"))

# # Move port tuners to target Gamma for this control frequency
write("PORT:LOAD:TUNE 0.9, 45")
print(query("*OPC?"))
# Read back the computed port Gamma, S-Parameters and position
print(query("PORT:LOAD:GAMMA?"))
print(query("PORT:LOAD:TUNE:POS?"))
checkError()
#endregion

mTune.close()