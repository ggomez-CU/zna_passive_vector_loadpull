clear all
close all
clc

data_test_VNA_atten = readtable("20251215_6GHz.csv");
% 1port_cal_filename	2port_cal_filename	atten	corr_gamma_out.gamma_L.angle_rad	corr_gamma_out.gamma_L.imag	corr_gamma_out.gamma_L.mag	corr_gamma_out.gamma_L.real	corr_gamma_out.gamma_S.angle_rad	corr_gamma_out.gamma_S.imag	corr_gamma_out.gamma_S.mag	corr_gamma_out.gamma_S.real	gamma.angle_rad	gamma.mag	idx	point.gamma_deg	point.gamma_mag	s11.imag	s11.real	s11_polar.angle_rad	s11_polar.mag	schema	setup_filename	step	sweep_file	sweep_info.count	test	test_frequency	ts	wave_data.a1.imag	wave_data.a1.real	wave_data.a2.imag	wave_data.a2.real	wave_data.b1.imag	wave_data.b1.real	wave_data.b2.imag	wave_data.b2.real	wave_data.x.type	wave_data.x.x_data

s2p_data = sparameters('20251215_thru.s2p');
thru_phase = angle(s2p_data.Parameters(1,2,:));
thru_mag = abs(s2p_data.Parameters(1,2,:));
frequency = data_test_VNA_atten.test_frequency(1);
freq_idx = find(s2p_data.Frequencies./1e9 == frequency);
freq_phase = thru_phase(freq_idx);
freq_mag = thru_mag(freq_idx);

atten = rmmissing(unique(data_test_VNA_atten.atten));
for atten_idx = 1:length(atten)
    figure
    rf = rowfilter(data_test_VNA_atten);
    data = data_test_VNA_atten(data_test_VNA_atten.atten == atten(atten_idx),:);

    subplot(2,2,1)
    polar(data.corr_gamma_out_gamma_L_angle_rad,data.corr_gamma_out_gamma_L_mag)
    hold on
    polar(data.s11_polar_angle_rad,data.s11_polar_mag)
    polar(data.s11_polar_angle_rad-2*freq_phase,(data.s11_polar_mag*freq_mag))
    polar(deg2rad(data.point_gamma_deg),data.point_gamma_mag)
    
    phase_s11_corr = unwrap(data.corr_gamma_out_gamma_L_angle_rad)-unwrap(data.s11_polar_angle_rad);
    
    subplot(2,2,2)
    plot(unwrap(data.corr_gamma_out_gamma_L_angle_rad)/pi*180)
    hold on
    plot(unwrap(data.s11_polar_angle_rad)/pi*180)
    yyaxis right
    plot(phase_s11_corr/pi*180)
    legend("a2/b2","measured s11 (varied atten)","phase seperation(rad)")
    
    subplot(2,2,3)
    plot(data.corr_gamma_out_gamma_L_mag)
    hold on
    plot(data.s11_polar_mag)
    plot(data.point_gamma_mag)
    legend("a2/b2","set value","measured s11 (varied atten)")

    subplot(2,2,4)
    deltathru = data.corr_gamma_out_gamma_L_mag.*exp(1i*data.corr_gamma_out_gamma_L_angle_rad)...
        -(data.s11_polar_mag*freq_mag).*exp(1i*(data.s11_polar_angle_rad-2*freq_phase));
    plot(10*log10(abs(deltathru)))
    10*log10(rmse(data.corr_gamma_out_gamma_L_mag.*exp(1i*data.corr_gamma_out_gamma_L_angle_rad),...
        data.s11_polar_mag.*exp(1i*(data.s11_polar_angle_rad-2*freq_phase))))
end

freq_phase/pi*180
