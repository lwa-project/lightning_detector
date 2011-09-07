#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
spinningCan.py - Python script for reading in serial port data from a Boltek EFM-100 
atmospheric electric field monitor and printing out the electric field and it change.

$Rev$
$LastChangedBy$
$LastChangedDate$
"""

import re
import sys
import numpy
import serial
import socket
import getopt
import threading
from time import sleep
from datetime import datetime, timedelta

from efield import ElectricField

# Electric field string regular expression
fieldRE = re.compile('\$(?P<field>[-+]\d{2}\.\d{2}),(?P<status>\d)\*(?P<checksum>[0-9A-F]{2})')

# Date formating string
dateFmt = "%Y-%m-%d %H:%M:%S.%f"


def usage(exitCode=None):
	print """spinningCan.py - Read data from a Boltek EFM-100 atmosphereic 
electric field monintor and broadcast field change and lightning events via UDP
multi-cast.

Usage: spinningCan.py [OPTIONS]

Options:
-h, --help                  Display this help information
-c, --config-file           Path to configuration file
-r, --record-to             Record the raw electric field data to a file
"""

	if exitCode is not None:
		sys.exit(exitCode)
	else:
		return True


def parseOptions(args):
	config = {}
	config['configFile'] = 'lightning.cfg'
	config['recordFile'] = None

	try:
		opts, args = getopt.getopt(args, "hc:r:", ["help", "config-file=", "record-to="])
	except getopt.GetoptError, err:
		# Print help information and exit:
		print str(err) # will print something like "option -a not recognized"
		usage(exitCode=2)
	
	# Work through opts
	for opt, value in opts:
		if opt in ('-h', '--help'):
			usage(exitCode=0)
		elif opt in ('-c', '--config-file'):
			config['configFile'] = str(value)
		elif opt in('-r', '--record-to'):
			config['recordFile'] = str(value)
		else:
			assert False
	
	# Add in arguments
	config['args'] = args

	# Parse the configuration file
	cFile = parseConfigFile(config['configFile'])
	for k,v in cFile.iteritems():
		config[k] = v

	# Return configuration
	return config


def parseConfigFile(filename):
	"""
	Given the name of a configuration file, parse it and return a dictionary of
	the configuration parameters.  If the file doesn't exist or can't be opened,
	return the default values.
	"""

	config = {}

	config['SERIAL_PORT'] = "/dev/ttyS0"
	config['MCAST_ADDR']  = "224.168.2.9"
	config['MCAST_PORT']  = 7163
	config['SEND_PORT']   = 7164
	
	config['FIELD_AVERAGE']          = 1.0
	config['HIGH_FIELD']             = 5.0
	config['VERY_HIGH_FIELD']        = 7.0
	config['FIELD_REPORT_INTERVAL']  = 1.0
	config['FIELD_CLEARED_INTERVAL'] = 1.0

	config['LIGHTNING_MIN_FIELD_CHANGE'] = 0.05
	config['LIGHTNING_REPORT_INTERVAL']  = 0.83
	config['LIGHTNING_CLEARED_INTERVAL'] = 2.00

	try:
		fh = open(filename, 'r')
		for line in fh:
			line = line.replace('\n', '')
			if len(line) < 3:
				continue
			if line[0] == '#':
				continue

			keyword, value = line.split(None, 1)
			config[keyword] = value
	except Exception as err:
		print "WARNING:  could not parse configuration file '%s': %s" % (filename, str(err))

	return config


def computeChecksum(text):
	"""
	Compute the checksum for the output string using the first 10 characters.
	Return the checksum as a string for easy comparision in parseField.
	"""
	
	cSum = 0
	for c in text[:10]:
		cSum += ord(c)
		cSum %= 256
		
	return "%2X" % cSum


def parseField(text):
	"""
	Parse the output string with the format:
	  $<p><ee.ee>,<f>*<cs><cr><lf>
	  
	  <p> - polarity of electric field + or -
	  <ee.ee> - electric field level 00.00 to 20.00
	  <f> - fault 0: Normal, 1: Rotor Fault
	  <cs> - checksum in hex 00 to FF
	  <cr> - carriage return
	  <lf> - line feed
	  
	And return a three-element tuple of the field string, status code, and 
	a boolean of whether or not the data are valid.
	"""

	mtch = fieldRE.match(text)

	try:
		field = float(mtch.group('field'))
		status = int(mtch.group('status'))
		valid = True if mtch.group('checksum') == computeChecksum(text) else False
	except:
		field = 0.0
		status = 2
		valid = False
		
	return field, status, valid


class dataServer(object):
	def __init__(self, mcastAddr="224.168.2.9", mcastPort=7163, sendPort=7164):
		self.sendPort  = sendPort
		self.mcastAddr = mcastAddr
		self.mcastPort = mcastPort
		
		self.sock = None
		
	def start(self):
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
		#The sender is bound on (0.0.0.0:7164)
		self.sock.bind(("0.0.0.0", self.sendPort))
		#Tell the kernel that we want to multicast and that the data is sent
		#to everyone (255 is the level of multicasting)
		self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 20)
		
	def stop(self):
		if self.sock is not None:
			self.sock.close()
			self.sock = None
		
	def send(self, data):
		if self.sock is not None:
			self.sock.sendto(data, (self.mcastAddr, self.mcastPort) )


def main(args):
	config = parseOptions(args)
	
	# Setup the recording option.  If we aren't supposed to record, set
	# `rFH` to None so that we can safely skip over it in the code.
	if config['recordFile'] is not None:
		rFH = open(config['recordFile'], 'a')
	else:
		rFH = None
	
	# Set the field
	movingField = ElectricField()
	movingField.updateConfig(config)

	# Start the data server
	server = dataServer(mcastAddr=config['MCAST_ADDR'], mcastPort=int(config['MCAST_PORT']), 
				sendPort=int(config['SEND_PORT']))
	server.start()

	# Set the warning suppression interval
	fieldHigh = False
	lightningDetected = False
	fieldInterval = timedelta(0, 60*int(float(config['FIELD_REPORT_INTERVAL'])))
	fieldClearedInterval = timedelta(0, 60*int(float(config['FIELD_CLEARED_INTERVAL'])))
	lightningInterval = timedelta(0, 60*int(float(config['LIGHTNING_REPORT_INTERVAL'])))
	lightningClearedInterval = timedelta(0, 60*int(float(config['LIGHTNING_CLEARED_INTERVAL'])))
	
	lastFieldEvent = None
	lastLightningEvent = None

	# Read from the serial port forever (or at least until a keyboard interrupt has
	# been sent).
	try:
		c = 0
		while True:
			t = datetime.now()
			f = numpy.random.randn(1)[0] * 0.01
			if rFH is not None:
					rFH.write("%s  %+7.3f kV/m\n" % (t.strftime(dateFmt), f))
			
			# Add it to the list
			movingField.append(t, f)
			
			# Send out field and change notices
			c += 1
			if c % movingField.nKeep:
				server.send("[%s] FIELD: %+.3f kV/m" % (t.strftime(dateFmt), movingField.mean()))
				server.send("[%s] DELTA: %+.3f kV/m" % (t.strftime(dateFmt), movingField.deriv()))
				
				c = 0
			
			# Issue field warnings, if needed
			fieldText = None
			if movingField.isVeryHigh():
				if lastFieldEvent is None:
					fieldText = "[%s] WARNING: very high field" % t.strftime(dateFmt)
					lastFieldEvent = t
				elif t >= lastFieldEvent + fieldInterval:
					fieldText = "[%s] WARNING: very high field" % t.strftime(dateFmt)
					lastFieldEvent = t
				else:
					pass
				
				fieldHigh = True
				
			elif movingField.isHigh():
				if lastFieldEvent is None:
					fieldText = "[%s] WARNING: high field" % t.strftime(dateFmt)
					lastFieldEvent = t
				elif t >= lastFieldEvent + fieldInterval:
					fieldText = "[%s] WARNING: high field" % t.strftime(dateFmt)
					lastFieldEvent = t
				else:
					pass
				
				fieldHigh = True
				
			else:
				if lastFieldEvent is None:
					pass
				elif t >= lastFieldEvent + fieldClearedInterval and fieldHigh:
					fieldText = "[%s] NOTICE: High field cleared" % t.strftime(dateFmt)
					fieldHigh = False
				else:
					pass
			
			# Issue lightning warnings, if needed
			lightningText = None
			if movingField.isLightning():
				if lastLightningEvent is None:
					lightningText = "[%s] LIGHTNING: %.1f km" % (t.strftime(dateFmt), movingField.getLightningDistance())
					lastLightningEvent = t
				elif t >= lastLightningEvent + lightningInterval:
					lightningText = "[%s] LIGHTNING: %.1f km" % (t.strftime(dateFmt), movingField.getLightningDistance())
					lastLightningEvent = t
				
				lightningDetected = True
				
			else:
				if lastLightningEvent is None:
					pass
				elif t >= lastLightningEvent + lightningClearedInterval and lightningDetected:
					fieldText = "[%s] NOTICE: lightning cleared" % t.strftime(dateFmt)
					lightningDetected = False
				else:
					pass
					
			if fieldText is not None:
				print fieldText
				server.send(fieldText)
				
			if lightningText is not None:
				print lightningText
				server.send(lightningText)
				
			sleep(0.05 - (datetime.utcnow() - t))
				
	except KeyboardInterrupt:
		server.stop()
		print ''


if __name__ == "__main__":
	main(sys.argv[1:])
