#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
spinningCan.py - Python script for reading in serial port data from a Boltek EFM-100 
atmospheric electric field monitor and printing out the electric field and it change.
"""

from __future__ import print_function

import re
import sys
import json
import numpy
import serial
import socket
import argparse
import threading
import json_minify
from time import time, sleep
from datetime import datetime, timedelta

from efield import ElectricField

# Electric field string regular expression
fieldRE = re.compile('\$(?P<field>[-+]\d{2}\.\d{2}),(?P<status>\d)\*(?P<checksum>[0-9A-F]{2})')

# Date formating string
dateFmt = "%Y-%m-%d %H:%M:%S.%f"


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
    # Set the field
    movingField = ElectricField()
    movingField.updateConfig(args.config_file)

    # Start the data server
    server = dataServer(mcastAddr=args.config_file['multicast']['ip'], mcastPort=int(args.config_file['multicast']['port']), 
                sendPort=int(args.config_file['multicast']['port']))
    server.start()

    # Set the warning suppression interval
    fieldHigh = False
    lightningDetected = False
    fieldInterval = timedelta(0, int(60*float(args.config_file['efield']['report_interval'])))
    fieldClearedInterval = timedelta(0, int(60*float(args.config_file['efield']['cleared_interval'])))
    lightningInterval = timedelta(0, int(60*float(args.config_file['lightning']['report_interval'])))
    lightningClearedInterval = timedelta(0, int(60*float(args.config_file['lightning']['cleared_interval'])))
    
    lastFieldEvent = None
    lastLightningEvent = None

    # Read from the serial port forever (or at least until a keyboard interrupt has
    # been sent).
    print("Replaying file '%s'" % args.filename)
    fh = open(args.filename, 'r')

    try:
        c = 0
        while True:
            tStart = time()
            
            try:
                line = fh.readline()
                t, f = line.split('  ', 1)
                t = datetime.strptime(t, dateFmt)
                f, junk = f.split(None, 1)
                f = float(f)
                #sleep(0.01)
            except Exception as e:
                print(str(e))
                break

            # Add it to the list
            movingField.append(t, f)
            
            # Send out field and change notices
            c += 1
            if c % movingField.nKeep == 0:
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
            
            # Actually send the message out over UDP
            if fieldText is not None:
                print(fieldText)
                server.send(fieldText)
                
            if lightningText is not None:
                print(lightningText)
                server.send(lightningText)
                
            print("Done with field work in %.1f ms" % ((time() - tStart)*1000))
                
    except KeyboardInterrupt:
        server.stop()
        print('')

    fh.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='read data from a pre-recorded electric field file and broadcast field change and lightning events via UDP multi-cast',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
            )
    parser.add_argument('filename', type=str,
                        help='electric field file to replay')
    parser.add_argument('-c', '--config-file', type=str, default='lightning.json',
                        help='filename for the configuration file')
    args = parser.parse_args()
    
    # Parse the configuration file
    with open(args.config_file, 'r') as ch:
        args.config_file = json.loads(json_minify.json_minify(ch.read()))
        
    main(args)
    
