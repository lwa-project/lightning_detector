#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Broadcast lightning data served up by spinningCan.py using TCP.
"""

from __future__ import print_function

import sys
import time
import select
import socket
import argparse
from datetime import datetime


# Date formating string
dateFmt = "%Y-%m-%d %H:%M:%S.%f"


# Multicast timeout in seconds
timeout = 5


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
    sock.settimeout(timeout)
    
    #setup the TCP connection handling
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('0.0.0.0', mcastPort))
    server.listen(5)
    server.setblocking(False)
    servers = [server,]
    connections, addresses = [], []
    
    # Main reading loop
    try:
        while True:
            try:
                data, addr = sock.recvfrom(1024)
            except socket.error as e:
                t = datetime.utcnow()
                data = "[%s] NODATA: No data received after %.1f s" % (t.strftime(dateFmt), timeout)
                try:
                    data = data.encode()
                except AttributeError:
                    pass
                    
            readable, writable, errored = select.select(servers, connections, [])
            for s in readable:
                if s is server:
                    client_socket, address = server.accept()
                    connections.append(client_socket)
                    addresses.append(address)
                    print("Connection from", address)
            for s in writable:
                try:
                    if data is not None:
                        s.send(data)
                except socket.error as e:
                    idx = connections.index(s)
                    print("Connection closed to", addresses[idx])
                    s.close()
                    del connections[idx]
                    del addresses[idx]
                    
                    
    except KeyboardInterrupt:
        server.close()
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
    args = parser.parse_args()
    
    EFM100(mcastAddr=args.address, mcastPort=args.port)
    
