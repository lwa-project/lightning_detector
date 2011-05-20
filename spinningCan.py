#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
spinningCan.py - Python script for reading in serial port data from a Boltek EFM-100 
atmospheric electric field monitor and printing out the electric field and it change.
"""

import re
import sys
import serial
import socket
import threading
from datetime import datetime, timedelta

# Electric field and lightning warning levels
HIGH_FIELD = 5.0
VERY_HIGH_FIELD = 7.0
LIGHTNING_MIN_FIELD_CHANGE = 0.05

# Electric field string regular expression
fieldRE = re.compile('\$(?P<field>[-+]\d{2}\.\d{2}),(?P<status>\d)\*(?P<checksum>[0-9A-F]{2})')


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


def highField(field):
	"""
	Given an electric field value, compare it against HIGH_FIELD and return True
	if it *is* a high field.
	"""
	
	if abs(field) > HIGH_FIELD:
		return True
	else:
		return False


def veryHighField(field):
	"""
	Given an electric field value, compare it against HIGH_FIELD and return True
	if it *is* a high field.
	"""
	
	if abs(field) > VERY_HIGH_FIELD:
		return True
	else:
		return False


def lightning(deltaField):
	"""
	Given a change in the electric field, compare it with LIGHTNING_MIN_FIELD_CHANGE
	and see if it could be related to lightning.  If so, calculate a distance using
	a 10 kV/m field change for lightning at 5 km.
	"""
	
	if abs(deltaField) > LIGHTNING_MIN_FIELD_CHANGE:
		distance = (10.0/abs(deltaField))**(1/3.) * 5
		return True, distance
	else:
		return False, 100.0


class dataServer(object):
	def __init__(self, recv=7163, send=7164):
		self.sendPort  = 7164
		self.mcastAddr = "224.168.2.9"
		self.mcastPort = 7163
		
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
	if len(args) == 0:
		portName = '/dev/ttyS0'
	else:
		portName = args[0]
	
	# Set the serial port parameters
	efm100 = serial.Serial()
	efm100.timeout = 0.5
	efm100.port = portName
	efm100.baudrate = 9600
	efm100.bytesize = 8
	efm100.stopbits = 1
	efm100.parity = 'N'
	
	# Set the field averaging options
	c = 0
	avgField  = 0.0
	avgDField = 0.0
	
	# Open the port and find the start of the data stream
	efm100.open()
	text = efm100.read(1)
	while text != '$':
		text = efm100.read(1)

	# Start the data server
	server = dataServer()
	server.start()

	# Set the warning suppression interval
	fieldHigh = False
	lightningDetected = False
	fieldInterval = timedelta(0, 60)
	fieldClearedInterval = timedelta(0, 60)
	lightningInterval = timedelta(0, 5)
	lightningClearedInterval = timedelta(0, 120)
	
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
				# interested in using parseField
				t = datetime.now()
				f, s, v = parseField(text)
				hF = highField(f)
				vF = veryHighField(f)
				try:
					dF = f-lastField
				except NameError:
					dF = 0
				l,d = lightning(dF)
				lastField = f
				
				# Average the field over 20 samples
				avgField += f
				avgDField += dF
				c += 1
				if c is 40:
					avgField /= c
					avgDField /= c
					
					server.send("[%s] FIELD: %+.3f kV/m" % (t.strftime("%Y-%m-%d %H:%M:%S"), avgField))
					server.send("[%s] DELTA: %+.3f kV/m" % (t.strftime("%Y-%m-%d %H:%M:%S"), avgDField))
					
					avgField = 0.0
					avgDField = 0.0
					c = 0
				
				# Issue field warnings, if needed
				fieldText = None
				if veryHighField(f):
					if lastFieldEvent is None:
						fieldText = "[%s] WARNING: very high field" % t.strftime("%Y-%m-%d %H:%M:%S")
					elif t >= lastFieldEvent + fieldInterval:
						fieldText = "[%s] WARNING: very high field" % t.strftime("%Y-%m-%d %H:%M:%S")
					else:
						pass
					
					fieldHigh = True
					lastFieldEvent = t
					
				elif highField(f):
					if lastFieldEvent is None:
						fieldText = "[%s] WARNING: high field" % t.strftime("%Y-%m-%d %H:%M:%S")
					elif t >= lastFieldEvent + fieldInterval:
						fieldText = "[%s] WARNING: high field" % t.strftime("%Y-%m-%d %H:%M:%S")
					else:
						pass
					
					fieldHigh = True
					lastFieldEvent = t
					
				else:
					if lastFieldEvent is None:
						pass
					elif t >= lastFieldEvent + fieldClearedInterval and fieldHigh:
						fieldText = "[%s] NOTICE: High field cleared" % t.strftime("%Y-%m-%d %H:%M:%S")
						fieldHigh = False
					else:
						pass
				
				# Issue lightning warnings, if needed
				lightningText = None
				if l:
					if lastLightningEvent is None:
						lightningText = "[%s] LIGHTNING: %.1f km" % (t.strftime("%Y-%m-%d %H:%M:%S"), d)
					elif t >= lastLightningEvent + lightningInterval:
						lightningText = "[%s] LIGHTNING: %.1f km" % (t.strftime("%Y-%m-%d %H:%M:%S"), d)
					
					lightningDetected = True
					lastLightningEvent = t
				else:
					if lastLightningEvent is None:
						pass
					elif t >= lastLightningEvent + lightningClearedInterval and lightningDetected:
						fieldText = "[%s] NOTICE: lightning cleared" % t.strftime("%Y-%m-%d %H:%M:%S")
						lightningDetected = False
					else:
						pass
						
				if fieldText is not None:
					print fieldText
					server.send(fieldText)
					
				if lightningText is not None:
					print lightningText
					server.send(lightningText)

				# Start the next loop
				text = efm100.read(1)
				
	except KeyboardInterrupt:
		efm100.close()
		server.stop()
		print ''


if __name__ == "__main__":
	main(sys.argv[1:])
