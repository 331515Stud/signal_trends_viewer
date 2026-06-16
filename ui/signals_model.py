import pyqtgraph as pg
import numpy as np
from scipy.fft import rfft
import logging
from Lib import pipestreamdbread as pdb
from Lib import read_record_by_time_thread as rec_read_trr

class SignalsModel:
    def __init__(self):
        self.current_data = {}
        self.current_device = ""
        self.colnameList = []
        self.current_table_timestamp_list = []
        self.current_rec_num = 0
        self.current_freq_range = (-1, -1)

    def load_record(self, device_name, colname_list, timestamp, callback):
        thread = rec_read_trr.ReadRecordThread(device_name, colname_list, timestamp)
        thread.result_signal.connect(lambda rec_dict: callback(rec_dict))
        thread.error_signal.connect(lambda err: logging.error(err))
        thread.start()

    def get_signals(self, in_data):
        rec = pdb.LogRecord(in_data)
        return rec.get_signals()

    def process_signal(self, signals, sampling=25600):
        channel_num = signals.shape[1]
        processed = []
        for i in range(channel_num):
            sig = signals[:, i]
            sig = sig - sig.mean()
            l = len(sig)
            time_len = l / sampling
            time = np.linspace(0., time_len, l)

            yf = rfft(sig)
            sl = len(yf)
            spectrum = np.abs(yf) / l
            step = (sampling / l)
            fr = np.arange(0, (sampling / 2) + 1, step)

            processed.append({
                'time': time,
                'signal': sig,
                'freq': fr,
                'spectrum': spectrum
            })
        return processed