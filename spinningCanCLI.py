#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Command line interface to the lightning data served up by spinningCan.py.

$Rev$
$LastChangedBy$
$LastChangedDate$
"""

from __future__ import print_function

import sys
import time
import socket
import argparse

import re
from datetime import datetime

dataRE = re.compile(r'^\[(?P<date>.*)\] (?P<type>[A-Z]*): (?P<data>.*)$')


def EFM100(mcastAddr="224.168.2.9", mcastPort=7163, print_field=False, print_warning=False):
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
                if print_field and (mtch.group('type') in ['FIELD', 'DELTA']):
                    print(data)
                if print_warning and mtch.group('type') in ['WARNING',]:
                    print(data)
                if mtch.group('type') in ['LIGHTNING', 'NOTICE']:
                    print(data)

            except socket.error, e:
                pass
                
    except KeyboardInterrupt:
        sock.close()
        print('')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='read data from a spinningCan.py lightning data server and print it',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
            )
    parser.add_argument('-a', '--address', type=str, default='224.168.2.9',
                        help='mulitcast address to connect to')
    parser.add_argument('-p', '--port', type=int, default=7163,
                        help='multicast port to connect on')
    parser.add_argument('-f', '--field', action='store_true',
                        help='print out electric field and field change information')
    parser.add_argument('-w', '--warning', action='store_true',
                        help='print out high field/very high field warnings')
    args = parser.parse_args()
    
    EFM100(mcastAddr=args.address, mcastPort=args.port, print_field=args.field, print_warning=args.warning)
    