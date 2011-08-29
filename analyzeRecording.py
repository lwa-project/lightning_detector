#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import pytz
import numpy
from datetime import datetime
from matplotlib import pyplot as plt


# MST7MDT
UTC = pytz.utc
MST = pytz.timezone('US/Mountain')

# Date formating string
dateFmt = "%Y-%m-%d %H:%M:%S.%f"

# Open the file and read it in
fh = open(sys.argv[1], 'r')

times = []
fields = []
while True:
	try:
		# Read a line and split it into a datetime string and a field measurement
		line = fh.readline()
		t, f = line.split('  ', 1)

		# Convert the time to datetime object (in MST/MDT) and the field to a float
		t = MST.localize(datetime.strptime(t, dateFmt))
		f, junk = f.split(None, 1)
		f = float(f)
		
		# Save
		times.append(t.astimezone(UTC))
		fields.append(f)

	except Exception, e:
		print "Reading ends with: %s" % str(e)
		break
fh.close()

# Convert the list of field strengths in kV/m to a numpy array
fields = numpy.array(fields)

# Boxcar smooth the field with a three sample window
fields2 = fields*0
for i in xrange(1,len(fields)-1):
	fields2[i] = (fields[i] + fields[i-1] + fields[i+1]) / 3.0
fields = fields2

# Differentiation by two methods:  simple and wide
deltas = fields - numpy.roll(fields, 1)
deltas2 = (numpy.roll(fields, -1) - numpy.roll(fields, 1)) / 2.0

# Plots
fig = plt.figure()
ax = fig.gca()
ax.plot_date(times, fields,  color='blue')
ax.plot_date(times, deltas,  color='green')
ax.plot_date(times, deltas2, color='red')

for i in xrange(len(deltas)):
	if numpy.abs(deltas[i]) > 0.04:
		ax.vlines(times[i], -20, 20, color='green', linestyle='--')
	if numpy.abs(deltas2[i]) > 0.04:
		ax.vlines(times[i], -20, 20, color='red', linestyle='--')
ax.set_ylim([-20, 20])

ax.set_title('spinningCan.py Recording "%s"' % sys.argv[1])
ax.set_xlabel('Time')
ax.set_ylabel('Electric Field [kV/m]')
fig.autofmt_xdate()
plt.show()

