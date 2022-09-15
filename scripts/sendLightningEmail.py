#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Command line interface to the lightning data served up by spinningCan.py.
"""

from __future__ import print_function

import os
import sys
import pytz
import time
import uuid
import socket
import argparse
import threading
from socket import gethostname

import smtplib
from email.mime.text import MIMEText

import re
from datetime import datetime, timedelta

dataRE = re.compile(r'^\[(?P<date>.*)\] (?P<type>[A-Z]*): (?P<data>.*)$')

# Site
SITE = gethostname().split('-', 1)[0]

# E-mail Users
TO = ['lwa1ops-l@list.unm.edu',]
CC = []

# SMTP user and password
if SITE == 'lwa1':
    FROM = 'lwa.station.1@gmail.com'
    PASS = 'rzsxktfuudvfeqsv'
elif SITE == 'lwasv':
    FROM = 'lwa.station.sv@gmail.com'
    PASS = 'xuyqpylcarzfyrlo'
    CC.append('jntille@sandia.gov')
elif SITE == 'lwana':
    FROM = 'lwa.station.na@gmail.com'
    PASS = 'xsphaddgntptmgqm'
else:
    raise RuntimeError("Unknown site '%s'" % SITE)

# Timezones
UTC = pytz.utc
MST = pytz.timezone('US/Mountain')


def sendEmail(subject, message, debug=False):
    """
    Send an e-mail via the LWA1 operator list
    """
    
    message = "%s\n\nEmail ID: %s" % (message, str(uuid.uuid4()))
    
    rcpt = []
    msg = MIMEText(message)
    msg['Subject'] = subject
    msg['From'] = FROM
    msg['To'] = ','.join(TO)
    
    rcpt.extend(TO)
    if len(CC):
        msg['Cc'] = ','.join(CC)
        rcpt.extend(CC)
        
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        if debug:
            server.set_debuglevel(1)
        server.starttls()
        server.login(FROM, PASS)
        server.sendmail(FROM, rcpt, msg.as_string())
        server.close()
        return True
    except Exception as e:
        print(str(e))
        return False


def sendWarning(limit, strikeList):
    """
    Send a `lightning in the vicinity` warnings.
    """
    
    tNow = datetime.utcnow()
    tNow = UTC.localize(tNow)
    tNow = tNow.astimezone(MST)
    
    tNow = tNow.strftime("%B %d, %Y %H:%M:%S %Z")
    
    subject = '%s - Lightning in Area' % (SITE.upper(),)
    message = """At %s lightning was found in the vicinity (<= %.1f km) of %s.\n\nDuring the last 10 minutes, 
%i strikes were seen at distances of %.1f to %.1f km from the station.""" % (tNow, limit, SITE.upper(), len(strikeList), min(strikeList), max(strikeList))
    
    return sendEmail(subject, message)


def sendClear(limit, clearTime):
    """
    Send an "all clear" e-mail.
    """
    
    tNow = datetime.utcnow()
    tNow = UTC.localize(tNow)
    tNow = tNow.astimezone(MST)
    
    tNow = tNow.strftime("%B %d, %Y %H:%M:%S %Z")
    
    subject = '%s - Lightning in Area - Cleared' % (SITE.upper(),)
    message = "At %s no lightning within %.1f km of %s has been seen for %i minutes." % (tNow, limit, SITE.upper(), clearTime)
    
    return sendEmail(subject, message)


def EFM100(mcastAddr="224.168.2.9", mcastPort=7163, distance_limit=15.0, rate_limit=5.0):
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

    # Setup the strike buffer for a 10 minute period (1 strike per second)
    strikes = {}
    
    # Setup lightning control variable
    isClose = False
    
    # Main reading loop
    try:
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                
                # RegEx matching for message date, type, and content
                try:
                    data = data.decode('ascii')
                except AttributeError:
                    pass
                mtch = dataRE.match(data)
                t = datetime.strptime(mtch.group('date'), "%Y-%m-%d %H:%M:%S.%f")
                
                # If we have a lightning strike, figure out it if is close
                # enough to warrant saving the strike info.
                if mtch.group('type') == 'LIGHTNING':
                    dist, junk = mtch.group('data').split(None, 1)
                    dist = float(dist)
                    
                    if dist <= distance_limit:
                        strikes[t] = dist
                        
                # Cull the list of old (>30 minutes) strikes
                pruneTime = t
                for k in strikes.keys():
                    if pruneTime - k > timedelta(0, 1800):
                        del strikes[k]
                        
                # If there are any strikes left in the list, see if we
                # are in a "close lighthing" condition (more than rate_limit
                # strikes in the last 10 minutes).
                if len(strikes) > 0:
                    l = []
                    for k in strikes.keys():
                        if pruneTime - k < timedelta(0, 600):
                            l.append(strikes[k])
                            
                    # Notify the users by e-mail and set the "close lightning"
                    # flag
                    if len(l) > rate_limit and not isClose:
                        op = threading.Thread(target=sendWarning, args=(distance_limit, l))
                        op.start()
                        isClose = True
                else:
                    # If the dictionary is empty and we were previously under
                    # lightning conditions, send the "all clear" and clear the
                    # "close lighthing" flag
                    if isClose:
                        op = threading.Thread(target=sendClear, args=(distance_limit, 30))
                        op.start()
                        isClose = False
                        
            except socket.error as e:
                pass
                
    except KeyboardInterrupt:
        sock.close()
        print('')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='read data from a spinningCan.py lightning data server and send out an e-mail if too many strikes happen too close to the site',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
            )
    parser.add_argument('-a', '--address', type=str, default='224.168.2.9',
                        help='mulitcast address to connect to')
    parser.add_argument('-p', '--port', type=int, default=7163,
                        help='multicast port to connect on')
    parser.add_argument('-i', '--pid-file', type=str,
                        help='file to write the current PID to')
    parser.add_argument('-d', '--distance', type=float, default=15,
                        help='distance limit in km to consider threatening')
    parser.add_argument('-r', '--rate', type=float, default=5,
                        help='rate per 10 minutes of strikes inside `d` to consider threatening')
    args = parser.parse_args()
    
    # PID file
    if args.pid_file is not None:
        fh = open(args.pid_file, 'w')
        fh.write("%i\n" % os.getpid())
        fh.close()
        
    EFM100(mcastAddr=args.address, mcastPort=args.port, distance_limit=args.distance, rate_limit=args.rate)
