#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import sys
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
import numpy
from datetime import datetime
from matplotlib import pyplot as plt

from efield import ElectricField

# MST7MDT
UTC = ZoneInfo('UTC')
MST = ZoneInfo('America/Denver')

# Date formating string
dateFmt = "%Y-%m-%d %H:%M:%S.%f"

# Open the file and read it in
fh = open(sys.argv[1], 'r')

# Create an ElecticField instance to mimic how spinningCan* deals with things
movingField = ElectricField()

times = []
fields = []
lightning = []
distances = []
while True:
    try:
        # Read a line and split it into a datetime string and a field measurement
        line = fh.readline()
        t, f = line.split('  ', 1)

        # Convert the time to datetime object (in MST/MDT) and the field to a float
        t = datetime.strptime(t, dateFmt).replace(tzinfo=UTC)
        f, junk = f.split(None, 1)
        f = float(f)
        
        # Save - part 1
        times.append(t)
        fields.append(f)
        
        # Save - part 2
        movingField.append(t, f)
        if movingField.isLightning():
            lightning.append(t)
            distances.append( movingField.getLightningDistance() )

    except Exception as e:
        print("Reading ends with: %s" % str(e))
        break
fh.close()

# Convert the list of field strengths in kV/m to a numpy array
fields = numpy.array(fields)

# Boxcar smooth the field with a three sample window
fields2 = fields*0
for i in xrange(2,len(fields)):
    fields2[i] = (fields[i-2] + fields[i-1] + fields[i]) / 3.0
#fields = fields2

# Differentiation
deltas = fields - numpy.roll(fields, 7)

# Plots
fig = plt.figure()
ax = fig.gca()
ax.plot_date(times, fields,  color='blue')
ax.plot_date(times, deltas,  color='red')

for t,d in zip(lightning, distances):
    if d < 15:
        print(str(t.astimezone(MST)), "%.1f" % d)
    ax.vlines(t, -20, 20, color='red', linestyle='--')
ax.set_ylim([-20, 20])

ax.set_title('spinningCan.py Recording "%s"' % sys.argv[1])
ax.set_xlabel('Time')
ax.set_ylabel('Electric Field [kV/m]')
fig.autofmt_xdate()
plt.show()

