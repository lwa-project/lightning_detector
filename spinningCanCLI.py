#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Command line interface to the lightning data served up by spinningCan.py.

$Rev$
$LastChangedBy$
$LastChangedDate$
"""

import sys
import time
import getopt
import socket

import re
from datetime import datetime

dataRE = re.compile(r'^\[(?P<date>.*)\] (?P<type>[A-Z]*): (?P<data>.*)$')


def usage(exitCode=None):
	print """spinningCanCLI.py - Read data from a spinningCan.py lightning data 
server and print out the data.

Usage: spinningCanCLI.py [OPTIONS]

Options:
-h, --help                  Display this help information
-a, --address               Mulitcast address to connect to (default = 224.168.2.9)
-p, --port                  Multicast port to connect on (default = 7163)
-f, --field                 Print out electric field and field change information 
                            (default = No)
-w, --warnings              Print out high field/very high field warnings (default = No)
-l, --lightning             Print out lightning warnings and distances (default = Yes)
-e, --everything            Print out all data coming from the data server, equivalent
                            to -f -w -l.
"""

	if exitCode is not None:
		sys.exit(exitCode)
	else:
		return True


def parseOptions(args):
	config = {}
	config['addr'] = "224.168.2.9"
	config['port'] = 7163
	config['field'] = False
	config['warnings'] = False
	config['lightning'] = True

	try:
		opts, args = getopt.getopt(args, "ha:p:fwle", ["help", "address=", "port=", "field", "warnings", "lightning", "everything"])
	except getopt.GetoptError, err:
		# Print help information and exit:
		print str(err) # will print something like "option -a not recognized"
		usage(exitCode=2)
	
	# Work through opts
	for opt, value in opts:
		if opt in ('-h', '--help'):
			usage(exitCode=0)
		elif opt in ('-a', '--address'):
			config['addr'] = str(value)
		elif opt in ('-p', '--port'):
			config['port'] = int(value)
		elif opt in ('-f', '--field'):
			config['field'] = True
		elif opt in ('-w', '--warnings'):
			config['warnings'] = True
		elif opt in ('-l', '--lightning'):
			config['lightning'] = True
		elif opt in ('-e', '--everything'):
			config['field'] = True
			config['warnings'] = True
			config['lightning'] = True
		else:
			assert False
	
	# Add in arguments
	config['args'] = args

	# Return configuration
	return config


def EFM100(mcastAddr="224.168.2.9", mcastPort=7163):
	"""
	Function responsible for reading the UDP multi-cast packets and printing them
	to the screen.
	"""
	
	#create a UDP socket
	sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
	#allow multiple sockets to use the same PORT number
	sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
	#Bind to the port that we know will receive multicast data
	sock.bind(("0.0.0.0", mcastPort))
	#tell the kernel that we are a multicast socket
	sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 20)
	#Tell the kernel that we want to add ourselves to a multicast group
	#The address for the multicast group is the third param
	status = sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
			socket.inet_aton(mcastAddr) + socket.inet_aton("0.0.0.0"))
	sock.setblocking(1)

	# Main reading loop
	try:
		while True:
			try:
				data, addr = sock.recvfrom(1024)

				mtch = dataRE.match(data)
				if config['field'] and (mtch.group('type') in ['FIELD', 'DELTA']):
					print data
				if config['warnings'] and mtch.group('type') in ['WARNING',]:
					print data
				if config['lightning'] and mtch.group('type') in ['LIGHTNING', 'NOTICE']:
					print data

			except socket.error, e:
				pass
				
	except KeyboardInterrupt:
		sock.close()
		print ''


if __name__ == "__main__":
	config = parseOptions(sys.argv[1:])

	EFM100(mcastAddr=config['addr'], mcastPort=config['port'])
	
