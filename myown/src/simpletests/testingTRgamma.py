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
    return [directivity + (tracking*T/R)/(1-port_match*T/R)]

def ab2gamma1(T,R,directivity,tracking,port_match):
    # eq from hackborn. extrapolated equation 
    return [1/(directivity + (tracking*T/R)/(1-port_match*T/R))]

plt.ion() 

pna = Agilent_PNA_E8300("GPIB1::16::INSTR")
pna.init_loadpull()

directivityfile = np.genfromtxt("../data/errordata/LPvalidation/ErrorTerm_22_EDir.csv", 
delimiter=" ")
directivity = np.array([complex(float(re), float(im)) for re, im in zip(directivityfile[:401:2,1], directivityfile[:401:2,2])])
trackingfile = np.genfromtxt("../data/errordata/LPvalidation/ErrorTerm_22_ERft.csv", 
delimiter=" ")
tracking = np.array([complex(float(re), float(im)) for re, im in zip(trackingfile[:401:2,1], trackingfile[:401:2,2])])
port_matchfile = np.genfromtxt("../data/errordata/LPvalidation/ErrorTerm_22_ESrm.csv", 
delimiter=" ")
port_match = np.array([complex(float(re), float(im)) for re, im in zip(port_matchfile[:401:2,1], port_matchfile[:401:2,2])])

directivityfile = np.genfromtxt("../data/errordata/LPvalidation/ErrorTerm_11_EDir.csv", 
delimiter=" ")
directivity1 = np.array([complex(float(re), float(im)) for re, im in zip(directivityfile[:401:2,1], directivityfile[:401:2,2])])
trackingfile = np.genfromtxt("../data/errordata/LPvalidation/ErrorTerm_11_ERft.csv", 
delimiter=" ")
tracking1 = np.array([complex(float(re), float(im)) for re, im in zip(trackingfile[:401:2,1], trackingfile[:401:2,2])])
port_matchfile = np.genfromtxt("../data/errordata/LPvalidation/ErrorTerm_11_ESrm.csv", 
delimiter=" ")
port_match1 = np.array([complex(float(re), float(im)) for re, im in zip(port_matchfile[:401:2,1], port_matchfile[:401:2,2])])


# Set up the polar plot
fig, ax = plt.subplots() #subplot_kw={'projection': 'polar'})
ax.grid(True)
# ax.set_title("Polar Plot of S11 and Gamma", va='bottom')

# Initial dummy plots (must unpack the line from plot())
line1, = ax.plot([0,1], [0,801], marker='o', linewidth=0,label='Gamma')
# line1, = ax.plot([], [], marker='o', ms=2, linewidth=0,label='Gamma')
# line2, = ax.plot([], [], marker='o', ms=1, linewidth=0,label='S11')
ax.legend()

# Interactive update loop


for i in range(500):
    s11 = pna.get_trace_data_raw(5)
    # T = pna.get_trace_data_raw(1)
    # R = pna.get_trace_data_raw(2)
    # gamma1 = ab2gamma1(T, R, port_match1, tracking1, directivity1)
    T = pna.get_trace_data_raw(3)
    R = pna.get_trace_data_raw(4)
    gamma = ab2gamma(T, R, port_match, tracking, directivity)
    # # Update data in polar format (theta = angle, radius = magnitude)
    # line2.set_data(np.angle(s11), np.abs(s11))
    # line1.set_data(np.angle(gamma), np.abs(gamma))
    line1.set_data(np.abs(np.abs(s11-gamma)),range(len(gamma[0])))
    plt.pause(3)
    fig.canvas.draw()
    fig.canvas.flush_events()
    print(i)
