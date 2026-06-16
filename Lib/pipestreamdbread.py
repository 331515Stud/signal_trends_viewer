from Lib import bytestransforms as bt
import psycopg2
from psycopg2 import Error
import base64
import datetime
import numpy as np
import logging
from dataclasses import dataclass

preamble_size = 3
cellsize = 3
minsize = 150

ADC_full_scale_V = 0.93
ADC_raw_max = (1 << 21)

db_connection_params = {"user": "lartech",
    "password": "lartech",
    "host": "10.78.1.95",
    "port": "5432",
    "database": "streampipedb"}

#=========================================================================================================
@dataclass
class Timerange:
    begin: int = 0
    end: int = 0
#=========================================================================================================
def connect_db(params):

    status="OK"

    try:
        connection = psycopg2.connect(user=db_connection_params["user"],
                                      password=db_connection_params["password"],
                                      host = db_connection_params["host"],
                                      port=db_connection_params["port"],
                                      database = db_connection_params["database"])

        cursor = connection.cursor()
        cursor.execute("SELECT version();")
        record = cursor.fetchone()
        logging.info(f"Подключение к БД: {record}")

    except (Exception, Error) as status:
        logging.error(f"Ошибка при работе с PostgreSQL: {status}")
        return 0, 0, str(status)

    return connection, cursor, str(status)
def get_logger_data_table_list(cursor):

    cursor.execute('''SELECT table_name FROM INFORMATION_SCHEMA.tables 
                    where table_schema = 'public' 
                    and regexp_like(table_name, 'logger_[0-9]*_data')''')

    logger_list =  cursor.fetchall()

    logger_list=[i[0] for i in logger_list] #убираем круглые скобки из ответа

    return logger_list
#-----------------------------------------------------------------------------------------------------
def get_table_row_num(cursor, tablename):

    query = f"SELECT COUNT(*) FROM {tablename};"
    cursor.execute(query)
    cnt = cursor.fetchone()
    return int(cnt[0])
#-----------------------------------------------------------------------------------------------------
def timestamp_from_iso(iso_time_str):
    dt = datetime.datetime.fromisoformat(iso_time_str)
    return int(dt.timestamp()*1000)
#-----------------------------------------------------------------------------------------------------
def datetime_from_timestamp(timestamp):
    datetime_obj = datetime.datetime.fromtimestamp(timestamp/1000) #под формат postgresql
    #iso_format_string = datetime_obj.isoformat()
    return datetime_obj
#-----------------------------------------------------------------------------------------------------
def get_record_list_with_filter(cursor, tablename: str, timerange: Timerange) -> list:
    check_begin = str(timerange.begin)
    check_end = str(timerange.end)

    if len(check_begin) != 13 or len(check_end) !=13:
        logging.error(f"Ошибка в get_record_list_with_filter: длинна штампа времени не равна 13")
        return []

    query = f'''SELECT timestamp FROM {tablename} 
            WHERE
            timestamp > {timerange.begin} AND
            timestamp < {timerange.end}'''

    cursor.execute(query)
    record_list =  cursor.fetchall()

    record_list=[i[0] for i in record_list] #убираем круглые скобки из ответа

    return record_list # возвращает список timestamp
#-----------------------------------------------------------------------------------------------------
def get_first_record(cursor, tablename: str) -> dict:

    colnames_list = get_column_names(cursor, tablename)
    colnames_str = ", ".join(colnames_list)

    query_first = f'''SELECT {colnames_str} FROM {tablename} 
            ORDER BY timestamp ASC
            LIMIT 1; '''

    cursor.execute(query_first)
    first_ans = cursor.fetchone()
    first_dict = dict(zip(colnames_list, first_ans))

    return first_dict
#-----------------------------------------------------------------------------------------------------
def get_last_record(cursor, tablename: str):

    colnames_list = get_column_names(cursor, tablename)
    colnames_str = ", ".join(colnames_list)

    query_last = f'''SELECT {colnames_str} FROM {tablename} 
            ORDER BY timestamp DESC
            LIMIT 1; '''

    cursor.execute(query_last)
    last_ans = cursor.fetchone()
    last_dict = dict(zip(colnames_list, last_ans))

    rec_num = get_table_row_num(cursor, tablename)

    return last_dict, rec_num, colnames_list
#-----------------------------------------------------------------------------------------------------
def get_records_list(cursor, tablename: str) -> list:
    query = f'''
        SELECT timestamp
        FROM {tablename}
        ORDER BY timestamp ASC
    '''

    cursor.execute(query)
    ans = cursor.fetchall()
    ret = [x[0] for x in ans]
    return ret
#-----------------------------------------------------------------------------------------------------
def get_column_names(cursor, tablename: str) -> list:
    query = f'''
        SELECT column_name
        FROM information_schema.columns 
        WHERE table_name = '{tablename}';    
    '''
    cursor.execute(query)
    colnames_list =  cursor.fetchall()
    colnames_list=[i[0] for i in colnames_list] #убираем круглые скобки из ответа

    return colnames_list
# -----------------------------------------------------------------------------------------------------
def get_table_description(cursor, tablename):

    colnames_list = get_column_names(cursor, tablename)

    table_cols_list = ["timestamp", "gps_latitude", "gps_longitude"]
    query_colnames = set(colnames_list).intersection(set(table_cols_list))
    colnames_str = ", ".join(query_colnames)
    query_first = f'''SELECT {colnames_str} FROM {tablename} 
            ORDER BY timestamp ASC
            LIMIT 1; '''

    query_last = f'''SELECT {colnames_str} FROM {tablename} 
            ORDER BY timestamp DESC
            LIMIT 1; '''

    query_rec_num = f'''SELECT COUNT(*)
            FROM {tablename};'''

    cursor.execute(query_first)
    first_ans = cursor.fetchone()
    first_dict = dict(zip(query_colnames, first_ans))


    cursor.execute(query_last)
    last_ans = cursor.fetchone()
    last_dict = dict(zip(query_colnames, last_ans))

    cursor.execute(query_rec_num)
    rec_num = int(cursor.fetchone()[0])

    table_description = {}

    table_description["device"] = tablename
    if "timestamp" in first_dict:
        table_description["first_records"] = first_dict["timestamp"]
    else:
        table_description["first_records"] = ""

    if "timestamp" in last_dict:
        table_description["last_records"] = last_dict["timestamp"]
    else:
        table_description["last_records"] = ""

    Lat1 = Lat2 = Long1 = Long2 = 0.0

    if "gps_latitude" in first_dict:
        Lat1 = float(first_dict["gps_latitude"])

    if "gps_longitude" in first_dict:
        Long1 = float(first_dict["gps_longitude"])

    if "gps_latitude" in last_dict:
        Lat2 = float(last_dict["gps_latitude"])

    if "gps_latitude" in last_dict:
        Long2 = float(last_dict["gps_longitude"])

    Lat= max(Lat1, Lat2)
    Long = max(Long1, Long2)

    if "gps_latitude" in first_dict:
        table_description["gps_latitude"] = Lat
        table_description["gps_longitude"] = Long
    else:
        table_description["gps_latitude"] = ""
        table_description["gps_longitude"] = ""

    table_description["record_num"] = rec_num

    return table_description


#-----------------------------------------------------------------------------------------------------
def get_record(cursor, tablename:str, timestamp, colnames_list):

    colnames_str = ", ".join(colnames_list)

    query = f'''SELECT {colnames_str} FROM {tablename} 
            WHERE
            timestamp = {timestamp}'''

    cursor.execute(query)
    record_tuple =  cursor.fetchone()

    record_dict = dict(zip(colnames_list, record_tuple))

    return record_dict
#=========================================================================================================
@dataclass
class LogRecord:
    rec: dict
        
    def get_signals(self):
        
        mask = self.rec["mask"]
        channels_num = mask.count("1") #число единичек в строке - маске дает число каналов
    
        npoints = self.rec["npoints"] #число сэмплов
    
        byte_string = base64.b64decode(self.rec["points"]) #строка base64
    
        rec_len = npoints * cellsize * channels_num
    
        strlen = len(byte_string)
        if strlen < rec_len+preamble_size:
            logging.error("Ошибка размера массива точек в get_byte_string")
            return []
        
        signals = np.empty([npoints, channels_num])
        
        VoltMult = self.rec["cfg_voltage_multiplier"]
        VoltDiv = self.rec["cfg_voltage_divider"]

        CurrMult = self.rec["cfg_current_multiplier"]
        CurrDiv = self.rec["cfg_current_divider"]
        
        
        for i in range(npoints):
            a = i * cellsize * channels_num + preamble_size
            b = a + cellsize * channels_num
            sample = byte_string[a:b]


            for j in range(channels_num):
                c = j * cellsize
                d = c + cellsize

                adc_raw_value = bt.reverse_bytes_order(sample[c:d])
                adc_int = bt.bytesToIntBig(adc_raw_value)


                if j in range(3):
                    real_value =  ((VoltMult / VoltDiv ) / ( ADC_raw_max / ADC_full_scale_V )) * (adc_int >> 2) 
                else:
                    real_value = ((CurrMult / CurrDiv ) / ( ADC_raw_max / ADC_full_scale_V )) * (adc_int >> 2) 


                signals[i, j] = real_value
                
                
        return signals
    

    def get_record_dict(self) -> dict:
        return self.rec