clear all
close all
clc

function plot_thru_s2p(s2p_filename)
    s2p_data = sparameters(s2p_filename);
    thru_phase = angle(s2p_data.Parameters(1,2,:));
    thru_mag = abs(s2p_data.Parameters(1,2,:));
    subplot(1,2,1)
    hold on
    plot(s2p_data.Frequencies,10*log10(thru_mag(:)),'DisplayName',s2p_filename)
    subplot(1,2,2)
    hold on
    plot(s2p_data.Frequencies,thru_phase(:),'DisplayName',s2p_filename)
end

plot_thru_s2p('20251215_thru.s2p');
plot_thru_s2p('20251215_thru_5dB.s2p');
plot_thru_s2p('20251215_thru_10dB.s2p');
plot_thru_s2p('20251215_thru_15dB.s2p');
plot_thru_s2p('20251215_thru_20dB.s2p');
plot_thru_s2p('20251215_thru_25dB.s2p');
plot_thru_s2p('20251215_thru_30dB.s2p');
subplot(1,2,1)
legend
subplot(1,2,2)
legend
