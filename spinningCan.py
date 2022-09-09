#!/usr/bin/env python3

"""
spinningCan.py - Python script for reading in serial port data from a Boltek EFM-100 
atmospheric electric field monitor and printing out the electric field and it change.
"""

import os
import re
import sys
import json
import numpy
import serial
import socket
import argparse
import threading
import json_minify
from datetime import datetime, timedelta

from efield import ElectricField

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
    except OSError as e:
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
    except OSError as e:
        sys.stderr.write("fork #2 failed: (%d) %s\n" % (e.errno, e.strerror))
        sys.exit(1)

    # Now I am a daemon!

    # Redirect standard file descriptors.
    si = open(stdin, 'r')
    so = open(stdout, 'a+')
    se = open(stderr, 'a+')
    ## Make a time mark
    mark = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    so.write("===\nLaunched at %s\n===\n" % mark)
    se.write("===\nLaunched at %s\n===\n" % mark)
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())


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
        try:
            data = bytes(data, 'ascii')
        except TypeError:
            pass
        if self.sock is not None:
            self.sock.sendto(data, (self.mcastAddr, self.mcastPort) )


def alignDataStream(SerialPort):
    """
    Read from the SerialPort one byte at a time until we find a '$' (which marks
    the start of a EFM-100 data entry).  Return the dollar sign when we find it.
    """
    
    text = SerialPort.read(1)
    try:
        text = text.decode('ascii')
    except AttributeError:
        pass
    except UnicodeDecodeError:
        text = ''
    while text != '$':
        text = SerialPort.read(1)
        try:
            text = text.decode('ascii')
        except AttributeError:
            pass
        except UnicodeDecodeError:
            text = ''
            
    return text


def main(args):
    # PID file
    if args.pid_file is not None:
        fh = open(args.pid_file, 'w')
        fh.write("%i\n" % os.getpid())
        fh.close()
        
    # Set the serial port parameters
    efm100 = serial.Serial()
    efm100.timeout = 0.5
    efm100.port = args.config_file['serial_port']
    efm100.baudrate = 9600
    efm100.bytesize = 8
    efm100.stopbits = 1
    efm100.parity = 'N'
    
    # Setup the logging option.  If we aren't supposed to log, set `lFH` to
    # sys.stdout.
    if args.log_file is not None:
        lFH = open(args.log_file, 'a+')
    else:
        lFH = sys.stdout
    
    # Setup the recording option.  If we aren't supposed to record, set
    # `rFH` to sys.stderr.
    if args.record_to is not None:
        rFH = open(args.record_to, 'a+')
    else:
        rFH = sys.stderr
    
    # Set the field
    movingField = ElectricField()
    movingField.updateConfig(args.config_file)
    
    # Open the port and find the start of the data stream
    efm100.open()
    text = alignDataStream(efm100)
    try:
        text = text.decode('ascii')
    except AttributeError:
        pass
    except UnicodeDecodeError:
        text = ''
        
    # Start the data server
    server = dataServer(mcastAddr=args.config_file['multicast']['ip'], mcastPort=int(args.config_file['multicast']['port']), 
                        sendPort=int(args.config_file['multicast']['port'])+1)
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
    try:
        c = 0
        while True:
            if text:
                new_text = efm100.read(13)
                try:
                    new_text = new_text.decode('ascii')
                except AttributeError:
                    pass
                text = text + new_text.replace('\x00', '')
                text = text.replace('\r\n', '\n')
                
                # Parse the string and extract the various bits that we are
                # interested in using parseField and record it if needed
                t = datetime.utcnow()
                f, s, v = parseField(text)
                if v:
                    rFH.write("%s  %+7.3f kV/m\n" % (t.strftime(dateFmt), f))
                    rFH.flush()
                    
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
                if movingField.isLightning() and movingField.isHigh():
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
                    lFH.write("%s\n" % fieldText)
                    lFH.flush()
                    
                if lightningText is not None:
                    print(lightningText)
                    server.send(lightningText)
                    lFH.write("%s\n" % lightningText)
                    lFH.flush()
                    
                # Start the next loop.  If we don't get enough characters (because 
                # the detector has lost power, for instance).  Run the re-alignment
                # function again to try to get the stream back.
                text = efm100.read(1)
                if len(text) < 1:
                    text = alignDataStream(efm100)
                try:
                    text = text.decode('ascii')
                except AttributeError:
                    pass
                except UnicodeDecodeError:
                    text = ''
                    
    except KeyboardInterrupt:
        efm100.close()
        server.stop()
        
        try:
            rFH.close()
            lFH.close()
        except:
            pass
            
        print('')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='read data from a Boltek EFM-100 atmosphereic electric field monintor and broadcast field change and lightning events via UDP multi-cast',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
            )
    parser.add_argument('-c', '--config-file', type=str, default='lightning.json',
                        help='filename for the configuration file')
    parser.add_argument('-p', '--pid-file', type=str,
                        help='file to write the current PID to')
    parser.add_argument('-l', '--log-file', type=str,
                        help='file to log operational status to')
    parser.add_argument('-r', '--record-to', type=str,
                        help='record the raw electric field data to a file')
    parser.add_argument('-f', '--foreground', action='store_true',
                        help='run in the foreground, do not daemonize')
    args = parser.parse_args()
    
    # Parse the configuration file
    with open(args.config_file, 'r') as ch:
        args.config_file = json.loads(json_minify.json_minify(ch.read()))
        
    if not args.foreground:
        daemonize('/dev/null','/tmp/sc-stdout','/tmp/sc-stderr')
        
    main(args)
    
