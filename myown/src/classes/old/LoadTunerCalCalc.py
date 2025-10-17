import csv
import matplotlib.pyplot as plt
import numpy as np
import stats

class LoadTunerCalCalc:
    def __init__(self, filename, x_max, y_max, step_size):
        self.filename =filename
        self.readfile()
        self.linear_fitting_gamma(x_max,step_size)
        self.linear_fitting_phi(y_max,step_size)
        self.plotdata()

    def readfile(self):
        cal_data_temp = csv.DictReader(open(self.filename),delimiter='\t')
        self.x_pos = np.array([float(row['X pos']) for row in cal_data_temp]).flatten()
        cal_data_temp = csv.DictReader(open(self.filename),delimiter='\t')
        self.y_pos = np.array([float(row['Y pos']) for row in cal_data_temp]).flatten()
        cal_data_temp = csv.DictReader(open(self.filename),delimiter='\t')
        self.gamma_s11 = np.array([float(row['Gamma s11']) for row in cal_data_temp]).flatten()
        cal_data_temp = csv.DictReader(open(self.filename),delimiter='\t')
        self.phi_s11 = np.array([float(row['Phi s11']) for row in cal_data_temp]).flatten()

    def plotdata(self):
        plt.subplot(1,2,1)
        plt.scatter(self.y_pos, self.gamma_s11, label='Gamma Cal Points')
        plt.plot(self.y_pos_linear, self.gamma_linear , color='red', label=f'Linear fit: Gamma')
        plt.xlabel('Load Tuner X coordinate (um)')
        plt.ylabel('Gamma Magnitude (linear)')
        plt.legend()

        plt.subplot(1,2,2)
        plt.scatter(self.x_pos, self.phi_s11, label='Phi Cal Points')
        plt.plot( self.x_pos_linear, self.phi_linear , color='red', label=f'Linear fit: Phi')
        plt.xlabel('Load Tuner X coordinate (um)')
        plt.ylabel('Phi (degrees)')
        plt.legend()

        plt.title("First order linear calibration from FDCS calibration text file")
        plt.show(block=False)
        plt.pause(10)
        plt.close()

    def linear_fitting_gamma(self, y_max,step_size):
        idx = np.argwhere(self.gamma_s11 > .2)    
        coefficients = np.polyfit(self.gamma_s11[idx].flatten(), self.y_pos[idx].flatten(), deg=1)
        slope = coefficients[0]
        intercept = coefficients[1]

        num = int((y_max) / step_size + 1)
        self.gamma_linear = np.linspace(0,1,num)
        self.y_pos_linear = slope * self.gamma_linear + intercept

    def linear_fitting_phi(self, x_max,step_size):

        # plt.hist(self.phi_s11, bins=20)
        # plt.show()

        counts, bin_edges = np.histogram(self.phi_s11, bins=20)  # Create histogram with 20 bins
        max_count_index = np.argmax(counts)  # Find the bin with the highest count
        mode = (bin_edges[max_count_index] + bin_edges[max_count_index + 1]) / 2 # Calculate mode

        #filter phi
        phi_idx = np.argwhere(abs(self.phi_s11-mode) > 30)
        phi = self.phi_s11[phi_idx].flatten()
        x_pos = self.x_pos[phi_idx].flatten()
        idx = np.argsort(x_pos)
        phi = phi[idx]
        x_pos = x_pos[idx]
        step = np.mean(np.diff(x_pos))
        L = len(x_pos)
        cal_fft = np.fft.fft(phi)

        phi_idx_len = int(L/(np.argmax(abs(cal_fft[0:int(len(cal_fft)/2)]))))

        phi_idx_start = np.argwhere(phi > 160).flatten()[0]
        phi_start = phi[phi_idx_start]
        phi_delta = 0
        factor = 1
        phi_idx_stop = x_max
        try:
            while (phi_delta < 250 and factor > 0.5 and phi_idx_start < phi_idx_stop):
                phi_idx_stop = phi_idx_start+int(phi_idx_len*factor)
                phi_stop = phi[phi_idx_stop]
                phi_delta = abs(phi_start-phi_stop)
                factor = factor*0.99
            x_start = x_pos[phi_idx_start]
            x_stop = x_pos[phi_idx_stop]
        except:
            quit()

        coefficients = np.polyfit(np.array([phi_start, phi_stop]).flatten(),
                                  np.array([x_start, x_stop]).flatten(), 
                                  deg=1)
        slope = coefficients[0]
        intercept = coefficients[1]

        num = int(abs(x_stop-x_start + 200) / step_size + 1)
        self.phi_linear = np.linspace(-180,180,num)
        self.x_pos_linear = slope * self.phi_linear + intercept

    def linear_gamma_pos(self, gamma_desired):
        index = np.argmin(np.abs(self.gamma_linear-gamma_desired))
        return float(self.y_pos_linear[index])
    
    def linear_phi_pos(self, phase_desired):
        index = np.argmin(np.abs(self.phi_linear-phase_desired))
        return float(self.x_pos_linear[index])