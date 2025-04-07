import calendar
import datetime
import pathlib
import typing
from collections import defaultdict
from dataclasses import dataclass

import numpy

PATH = pathlib.Path(__file__).parent
LOGFILE = PATH / "_camonitor.log"

# typical camonitor log file line
# 9idcAERO:m12.RBV               2022-12-02 09:35:54.535389 8.84368  \n


@dataclass
class DataEvent:
    pv: str
    timestamp: float
    value: "typing.Any"  # str, number, ... whatever


def read_logs(logfile):
    buf = None
    with open(logfile, "r") as f:
        buf = defaultdict(list)  # pv: [DataEvent()]
        for line in f.readlines():
            parts = line.split()
            if len(parts) == 4:
                pv, ymd, hms_m, value = parts
                hms, micros = hms_m.split(".")
                if len(micros) != 6:
                    print(f"PROBLEM, micros is not 6 digits: {line.strip()=}")
                dt = datetime.datetime.fromisoformat(f"{ymd}T{hms}")
                ts = calendar.timegm(dt.timetuple()) + float(micros) / 1e6
                buf[pv].append(DataEvent(pv, ts, value))

    return buf


def analyze(buffer):
    for pv, entries in buffer.items():
        if pv.endswith(".RBV"):
            ts = numpy.array([e.timestamp for e in entries])
            dt = ts[1:] - ts[:-1]  # differences
            print(f"{pv=}  {1/dt.min()=}  {1/dt.max()=}")


def main():
    buf = read_logs(LOGFILE)
    for k, v in buf.items():
        print(f"{k=}  {len(v)=} camonitor events")
    analyze(buf)


if __name__ == "__main__":
    main()
