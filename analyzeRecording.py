#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import numpy
from datetime import datetime
from matplotlib import pyplot as plt


# Date formating string
dateFmt = "%Y-%m-%d %H:%M:%S.%f"

times = []
fields = []
fh = open(sys.argv[1], 'r')
while True:
	try:
		line = fh.readline()
		t, f = line.split('  ', 1)
		t = datetime.strptime(t, dateFmt)
		f, junk = f.split(None, 1)
		f = float(f)
		
		times.append(t)
		fields.append(f)

	except Exception, e:
		print str(e)
		break
fh.close()

fields = numpy.array(fields)

fields2 = fields*0
for i in xrange(1,len(fields)-1):
	fields2[i] = (fields[i] + fields[i-1] + fields[i+1]) / 3.0
fields = fields2

deltas = fields - numpy.roll(fields, 1)
deltas2 = (numpy.roll(fields, -1) - numpy.roll(fields, 1)) / 2.0

fig = plt.figure()
ax = fig.gca()
ax.plot(fields,  color='blue')
ax.plot(deltas,  color='green')
ax.plot(deltas2, color='red')

for i in xrange(len(deltas)):
	if numpy.abs(deltas[i]) > 0.04:
		ax.vlines(i, -20, 20, color='green', linestyle='--')
	if numpy.abs(deltas2[i]) > 0.04:
		ax.vlines(i, -20, 20, color='red', linestyle='--')

plt.show()

