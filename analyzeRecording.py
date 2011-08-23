#!/usr/bin/env python

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
deltas = fields - numpy.roll(fields, 1)
deltas2 = (numpy.roll(fields, -1) - numpy.roll(fields, 1)) / 2.0

fig = plt.figure()
ax = fig.gca()
ax.plot(fields)
ax.plot(deltas)
ax.plot(deltas2)
plt.show()

