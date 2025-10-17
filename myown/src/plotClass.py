class plotClass():
	
	def __init__(self, address:str):
                plt.close(fig) 
                fig = plt.figure(constrained_layout=True)
                axs = fig.subplot_mosaic([['Samplers','Samplers','Gamma'],[ 'MeasTable','MeasTable', 'MeasTable']],
                                per_subplot_kw={"Gamma": {"projection": "polar"}})
                axs['Gamma'].set_title('Gamma')
                axs['Samplers'].set_title('Samplers')
                axs['MeasTable'].set_title('Power Values')
                axs['Gamma'].grid(True)
                line = []
                line.append(axs['Gamma'].plot([], [], marker='o', ms=1, linewidth=0))
                fig.suptitle(f'PA Drive Up', fontsize=16)
                plots = {}


def updateplot(axs, line, data, coupling, idx, plots):
    keys_list = list(data.keys())

    columns = ('Power (dB/dBm)')
    rows = ['DUT Input (dBm)','DUT Output (dBm)','Gain','Pin','Sampler 1','Sampler 2']

    outputdBm =  round(data[keys_list[0]]['wave data']['output_bwave']['dBm_mag'][0]+coupling['output coupling'],3)
    inputdBm = round(data[keys_list[0]]['wave data']['input_awave']['dBm_mag'][0]+coupling['input coupling'],3)
    plots['set_power'] = np.append(plots['set_power'],inputdBm)
    plots['sampler1'] = np.append(plots['sampler1'],data[keys_list[0]]['Samplers']['1'])
    plots['sampler2'] = np.append(plots['sampler2'],data[keys_list[0]]['Samplers']['2'])

    load = complex(data[keys_list[0]]['load_gamma']['real'],data[keys_list[0]]['load_gamma']['imag'])

    plots['gammaload'] = np.append(plots['gammaload'],load)

    line[0][0].set_data([np.angle(plots['gammaload'])], [np.abs(plots['gammaload'])])
    line[2*idx+1][0].set_data(plots['set_power'],plots['sampler1'])
    line[2*idx+2][0].set_data(plots['set_power'],plots['sampler2'])
    axs['MeasTable'].cla()
    axs['MeasTable'].axis('off')
    axs['MeasTable'].table(cellText=[[inputdBm],
            [outputdBm],
            [outputdBm-inputdBm],
            [round(data[keys_list[0]]['Input Power'],3)],
            [round(data[keys_list[0]]['Samplers']['1'],3)],
            [round(data[keys_list[0]]['Samplers']['2'],3)]],
            rowLabels=rows,
            colLabels=columns,
            loc='center')
    return plots