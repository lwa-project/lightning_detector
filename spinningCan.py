#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
spinningCan.py - Python script for reading in serial port data from a Boltek EFM-100 
atmospheric electric field monitor and printing out the electric field and it change.

$Rev$
$LastChangedBy$
$LastChangedDate$
"""

import os
import re
import sys
import numpy
import serial
import socket
import getopt
import threading
from datetime import datetime, timedelta

# Electric field and lightning warning levels
HIGH_FIELD = 5.0
VERY_HIGH_FIELD = 7.0
LIGHTNING_MIN_FIELD_CHANGE = 0.05

# Electric field string regular expression
fieldRE = re.compile('\$(?P<field>[-+]\d{2}\.\d{2}),(?P<status>\d)\*(?P<checksum>[0-9A-F]{2})')

# Date formating string
dateFmt = "%Y-%m-%d %H:%M:%S.%f"


"""
This module is used to fork the current process into a daemon.
Almost none of this is necessary (or advisable) if your daemon
is being started by inetd. In that case, stdin, stdout and stderr are
all set up for you to refer to the network connection, and the fork()s
and session manipulation should not be done (to avoid confusing inetd).
Only the chdir() and umask() steps remain as useful.

From:
  http://code.activestate.com/recipes/66012-fork-a-daemon-process-on-unix/

References:
  UNIX Programming FAQ
    1.7 How do I get my program to act like a daemon?
        http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16

    Advanced Programming in the Unix Environment
      W. Richard Stevens, 1992, Addison-Wesley, ISBN 0-201-56317-7.
"""

def daemonize(stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
	"""
	This forks the current process into a daemon.
	The stdin, stdout, and stderr arguments are file names that
	will be opened and be used to replace the standard file descriptors
	in sys.stdin, sys.stdout, and sys.stderr.
	These arguments are optional and default to /dev/null.
	Note that stderr is opened unbuffered, so
	if it shares a file with stdout then interleaved output
	may not appear in the order that you expect.
	"""
	
	# Do first fork.
	try:
		pid = os.fork()
		if pid > 0:
			sys.exit(0) # Exit first parent.
	except OSError, e:
		sys.stderr.write("fork #1 failed: (%d) %s\n" % (e.errno, e.strerror))
		sys.exit(1)

	# Decouple from parent environment.
	os.chdir("/")
	os.umask(0)
	os.setsid()

	# Do second fork.
	try:
		pid = os.fork()
		if pid > 0:
			sys.exit(0) # Exit second parent.
	except OSError, e:
		sys.stderr.write("fork #2 failed: (%d) %s\n" % (e.errno, e.strerror))
		sys.exit(1)

	# Now I am a daemon!

	# Redirect standard file descriptors.
	si = file(stdin, 'r')
	so = file(stdout, 'a+')
	se = file(stderr, 'a+', 0)
	os.dup2(si.fileno(), sys.stdin.fileno())
	os.dup2(so.fileno(), sys.stdout.fileno())
	os.dup2(se.fileno(), sys.stderr.fileno())


def usage(exitCode=None):
	print """spinningCan.py - Read data from a Boltek EFM-100 atmosphereic 
electric field monintor and broadcast field change and lightning events via UDP
multi-cast.

Usage: spinningCan.py [OPTIONS]

Options:
-h, --help                  Display this help information
-c, --config-file           Path to configuration file
-p, --pid-file              File to write the current PID to
-u, --user-id               User ID to run as
-l, --log-file              File to log warnings/lightning detections to
-r, --record-to             Record the raw electric field data to a file
"""

	if exitCode is not None:
		sys.exit(exitCode)
	else:
		return True


def parseOptions(args):
	config = {}
	config['configFile'] = 'lightning.cfg'
	config['userID'] = os.getuid()
	config['pidFile'] = None
	config['logFile'] = None
	config['recordFile'] = None

	try:
		opts, args = getopt.getopt(args, "hc:u:p:l=r:", ["help", "config-file=", "user-id=", "pid-file=", "log-file=", "record-to="])
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
		elif opt in ('-u' '--user-id'):
			config['userID'] = int(value)
		elif opt in ('-p', '--pid-file'):
			config['pidFile'] = str(value)
		elif opt in ('-l', '--log-file'):
			config['logFile'] = str(value)
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


def highField(field, config):
	"""
	Given an electric field value, compare it against HIGH_FIELD and return True
	if it *is* a high field.
	"""
	
	if abs(field) > float(config['HIGH_FIELD']):
		return True
	else:
		return False


def veryHighField(field, config):
	"""
	Given an electric field value, compare it against HIGH_FIELD and return True
	if it *is* a high field.
	"""
	
	if abs(field) > float(config['VERY_HIGH_FIELD']):
		return True
	else:
		return False


def lightning(deltaField, config):
	"""
	Given a change in the electric field, compare it with LIGHTNING_MIN_FIELD_CHANGE
	and see if it could be related to lightning.  If so, calculate a distance using
	a 10 kV/m field change for lightning at 5 km.
	"""
	
	if abs(deltaField) > float(config['LIGHTNING_MIN_FIELD_CHANGE']):
		distance = (10.0/abs(deltaField))**(1/3.) * 5
		return True, distance
	else:
		return False, 100.0


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


def alignDataStream(SerialPort):
	"""
	Read from the SerialPort one byte at a time until we find a '$' (which marks
	the start of a EFM-100 data entry).  Return the dollar sign when we find it.
	"""
	
	text = SerialPort.read(1)
	while text != '$':
		text = SerialPort.read(1)
		
	return text


def main(args):
	config = parseOptions(args)
	
	# User ID
	try:
		os.setuid(config['userID'])
	except OSError, e:
		sys.stderr.write("setuid failed: (%d) %s\n" % (e.errno, e.strerror))
		sys.exit(1)
	
	# PID file
	if config['pidFile'] is not None:
		fh = open(config['pidFile'], 'w')
		fh.write("%i\n" % os.getpid())
		fh.close()
	
	# Set the serial port parameters
	efm100 = serial.Serial()
	efm100.timeout = 0.5
	efm100.port = config['SERIAL_PORT']
	efm100.baudrate = 9600
	efm100.bytesize = 8
	efm100.stopbits = 1
	efm100.parity = 'N'
	
	# Setup the logging option.  If we aren't supposed to log, set `lFH` to
	# sys.stdout.
	if config['logFile'] is not None:
		lFH = open(config['logFile'], 'a')
	else:
		lFH = sys.stdout
	
	# Setup the recording option.  If we aren't supposed to record, set
	# `rFH` to sys.stderr.
	if config['recordFile'] is not None:
		rFH = open(config['recordFile'], 'a')
	else:
		rFH = sys.stderr
	
	# Set the field averaging options
	c = 0
	avgLimit = int(round(float(config['FIELD_AVERAGE'])*20))
	if avgLimit < 3:
		avgLimit = 3
	movingField = numpy.zeros(avgLimit)
	
	# Open the port and find the start of the data stream
	efm100.open()
	text = alignDataStream(efm100)

	# Start the data server
	server = dataServer(mcastAddr=config['MCAST_ADDR'], mcastPort=int(config['MCAST_PORT']), 
				sendPort=int(config['SEND_PORT']))
	server.start()

	# Set the warning suppression interval
	fieldHigh = False
	lightningDetected = False
	fieldInterval = timedelta(0, int(60*float(config['FIELD_REPORT_INTERVAL'])))
	fieldClearedInterval = timedelta(0, int(60*float(config['FIELD_CLEARED_INTERVAL'])))
	lightningInterval = timedelta(0, int(60*float(config['LIGHTNING_REPORT_INTERVAL'])))
	lightningClearedInterval = timedelta(0, int(60*float(config['LIGHTNING_CLEARED_INTERVAL'])))
	
	lastFieldEvent = None
	lastLightningEvent = None

	# Read from the serial port forever (or at least until a keyboard interrupt has
	# been sent).
	try:
		while True:
			if text:
				text = text + efm100.read(13)
				text = text.replace('\r\n', '\n')
				
				# Parse the string and extract the various bits that we are
				# interested in using parseField and record it if needed
				t = datetime.utcnow()
				f, s, v = parseField(text)
				if v:
					rFH.write("%s  %+7.3f kV/m\n" % (t.strftime(dateFmt), f))
					rFH.flush()
				
				movingField[c % avgLimit] = f
				tempField = numpy.roll(movingField, -(c % avgLimit))[:4]
				dF = tempField[1:].mean() - tempField[:3].mean()

				movingField[c % avgLimit] = f
				tempField = numpy.roll(movingField, -(c % avgLimit))
				dF = tempField[1:4].mean() - tempField[0:3].mean()

				# Figure out high fields
				hF = highField(f, config)
				vF = veryHighField(f, config)
				l,d = lightning(dF, config)
					
				# Average the field over 20 samples
				c += 1
				if c == avgLimit:
					avgField = movingField.mean()
					avgDField = (movingField[1:] - movingField[:-1]).mean()
					
					server.send("[%s] FIELD: %+.3f kV/m" % (t.strftime(dateFmt), avgField))
					server.send("[%s] DELTA: %+.3f kV/m" % (t.strftime(dateFmt), avgDField))
					
					c = 0
				
				# Issue field warnings, if needed
				fieldText = None
				if vF:
					if lastFieldEvent is None:
						fieldText = "[%s] WARNING: very high field" % t.strftime(dateFmt)
						lastFieldEvent = t
					elif t >= lastFieldEvent + fieldInterval:
						fieldText = "[%s] WARNING: very high field" % t.strftime(dateFmt)
						lastFieldEvent = t
					else:
						pass
					
					fieldHigh = True
					
				elif hF:
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
				if l:
					if lastLightningEvent is None:
						lightningText = "[%s] LIGHTNING: %.1f km" % (t.strftime(dateFmt), d)
						lastLightningEvent = t
					elif t >= lastLightningEvent + lightningInterval:
						lightningText = "[%s] LIGHTNING: %.1f km" % (t.strftime(dateFmt), d)
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
						
				# Actually send the message out over UDP
				if fieldText is not None:
					print fieldText
					server.send(fieldText)
					lFH.write("%s\n" % fieldText)
					lFH.flush()
					
				if lightningText is not None:
					print lightningText
					server.send(lightningText)
					lFH.write("%s\n" % lightningText)
					lFH.flush()

				# Start the next loop.  If we don't get enough characters (because 
				# the detector has lost power, for instance).  Run the re-alignment
				# function again to try to get the stream back.
				text = efm100.read(1)
				if len(text) < 1:
					text = alignDataStream(efm100)
				
	except KeyboardInterrupt:
		efm100.close()
		server.stop()
		
		if rFH is not None:
			rFH.close()
		
		print ''


if __name__ == "__main__":
	daemonize('/dev/null','/dev/null','/dev/null')
	main(sys.argv[1:])
