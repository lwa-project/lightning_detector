#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Graphical interface to the lightning data served up by spinningCan.py.
"""

import sys
import time
import socket
import argparse

import wx
import threading

import re
from time import sleep
from datetime import datetime

import matplotlib
matplotlib.use('WXAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg
from matplotlib.dates import *
from matplotlib.ticker import *
import pylab

#----------------------------------------------------------------------
# Create an own event type, so that GUI updates can be delegated
# this is required as on some platforms only the main thread can
# access the GUI without crashing. wxMutexGuiEnter/wxMutexGuiLeave
# could be used too, but an event is more elegant.

SOCKETRX = wx.NewEventType()
# bind to serial data receive events
EVT_SOCKETRX = wx.PyEventBinder(SOCKETRX, 0)

class SocketRxEvent(wx.PyCommandEvent):
    eventType = SOCKETRX
    def __init__(self, windowID, data):
        wx.PyCommandEvent.__init__(self, self.eventType, windowID)
        self.data = data

    def Clone(self):
        self.__class__(self.GetId(), self.data)

#----------------------------------------------------------------------

dataRE = re.compile(r'^\[(?P<date>.*)\] (?P<type>[A-Z]*): (?P<data>.*)$')

ID_CLEAR        = wx.NewId()
ID_SAVEAS       = wx.NewId()
ID_SETTINGS     = wx.NewId()
ID_TERM         = wx.NewId()
ID_EXIT         = wx.NewId()


class EFM100(wx.Frame):
    """
    Simple terminal program for wxPython.
    """
    
    def __init__(self, parent, id, title, mcastAddr="224.168.2.9", mcastPort=7163):
        wx.Frame.__init__(self, parent, id, title=title, size=(800,800))
        
        self.timesF = []
        self.fields = []
        self.timesD = []
        self.deltas = []
        self.strikes1 = {}
        self.strikes2 = {}
        
        # Number of points to display in the plot window
        self.nKeep = 180
        
        self.mcastAddr = mcastAddr
        self.mcastPort = mcastPort

        self.sock = None
        self.thread = None
        self.alive = threading.Event()
        
        self.initUI()
        self.initEvents()
        self.Show()
        
        self.startThread()
        self.initPlot()
        
    def initUI(self):
        menubar =  wx.MenuBar()
        
        fileMenu = wx.Menu()
        fileMenu.Append(ID_CLEAR,   "&Clear", "", wx.ITEM_NORMAL)
        fileMenu.Append(ID_SAVEAS, "&Save Text As...", "", wx.ITEM_NORMAL)
        fileMenu.AppendSeparator()
        fileMenu.Append(ID_EXIT, "&Exit", "", wx.ITEM_NORMAL)
        menubar.Append(fileMenu, "&File")
        self.SetMenuBar(menubar)

        panel = wx.Panel(self, -1)
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.figure1 = Figure((4.0, 4.0), dpi=100)
        self.canvas1 = FigureCanvasWxAgg(self, -1, self.figure1)
        hbox.Add(self.canvas1, 1, wx.EXPAND)
        self.figure2 = Figure((4.0, 4.0), dpi=100)
        self.canvas2 = FigureCanvasWxAgg(self, -1, self.figure2)
        hbox.Add(self.canvas2, 1, wx.EXPAND)
        vbox.Add(hbox)

        self.textCtrl = wx.TextCtrl(self, -1, "", style=wx.TE_MULTILINE|wx.TE_READONLY)
        vbox.Add(self.textCtrl, 1, wx.EXPAND)
        
        self.SetSizer(vbox)
        self.SetAutoLayout(1)
        vbox.Fit(self)
            
    def initEvents(self):
        self.Bind(wx.EVT_MENU, self.onClear,  id = ID_CLEAR)
        self.Bind(wx.EVT_MENU, self.onSaveAs, id = ID_SAVEAS)
        self.Bind(wx.EVT_MENU, self.onExit,   id=ID_EXIT)
        
        self.Bind(EVT_SOCKETRX, self.onSocketRead)

    def startThread(self):
        """
        Start the receiver thread
        """
        
        ANY = "0.0.0.0"
        MCAST_ADDR = self.mcastAddr
        MCAST_PORT = self.mcastPort
        
        #create a UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        #allow multiple sockets to use the same PORT number
        self.sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        #Bind to the port that we know will receive multicast data
        self.sock.bind((ANY, MCAST_PORT))
        #tell the kernel that we are a multicast socket
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 20)
        #Tell the kernel that we want to add ourselves to a multicast group
        #The address for the multicast group is the third param
        status = self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                socket.inet_aton(MCAST_ADDR) + socket.inet_aton(ANY))
        self.sock.setblocking(1)
        
        self.thread = threading.Thread(target=self.SocketThread)
        self.thread.setDaemon(1)
        self.alive.set()
        self.thread.start()

    def stopThread(self):
        """
        Stop the receiver thread, wait util it's finished.
        """
        
        if self.thread is not None:
            self.alive.clear()          #clear alive event for thread
            self.thread.join()          #wait until thread has finished
            self.thread = None
        
        if self.sock is not None:
            self.sock.close()
            self.sock = None
        
    def initPlot(self):
        """
        Create the plotting window and everything it needs.
        """

        self.axes1 = self.figure1.gca()
        self.axes1.set_axis_bgcolor('white')
        self.figure1.subplots_adjust(left=0.25)

        self.axes2 = self.figure2.gca()
        self.axes2.set_axis_bgcolor('white')
        self.figure2.subplots_adjust(left=0.25)
        
        pylab.setp(self.axes1.get_xticklabels(), fontsize=8)
        pylab.setp(self.axes1.get_yticklabels(), fontsize=8)

        pylab.setp(self.axes2.get_xticklabels(), fontsize=8)
        pylab.setp(self.axes2.get_yticklabels(), fontsize=8)

        # plot the data as a line series, and save the reference 
        # to the plotted line series
        #
        self.plot1 = self.axes1.plot([2,], [0,], linewidth=1, color='green')[0]
        self.plot2 = self.axes2.plot([2,], [0,], linewidth=1, color='blue' )[0]

        self.axes1.set_xlabel('Time')
        self.axes1.set_ylabel('E-Field [kV/m]')
        self.axes1.xaxis.set_major_locator(LinearLocator(numticks=6))
        self.axes1.xaxis.set_major_formatter(DateFormatter("%H:%M:%S"))
        self.figure1.autofmt_xdate()

        self.axes2.set_xlabel('Time')
        self.axes2.set_ylabel('$\\Delta$ E-Field [kV/m]')
        self.axes2.xaxis.set_major_locator(LinearLocator(numticks=6))
        self.axes2.xaxis.set_major_formatter(DateFormatter("%H:%M:%S"))
        self.figure2.autofmt_xdate()
        
        self.canvas1.draw()

        self.canvas2.draw()
        
    def drawPlot(self):
        """
        Draw the plot.
        """
        
        xmin = self.timesF[0]
        xmax = self.timesF[-1]
        
        ymin1 = sorted(self.fields)[ 0] - 0.05
        if ymin1 > -0.05:
            ymin1 = -0.05
        ymax1 = sorted(self.fields)[-1] + 0.05
        if ymax1 < 0.1:
            ymax1 = 0.1

        ymin2 = sorted(self.deltas)[ 0] - 0.05
        if ymin2 > -0.05:
            ymin2 = -0.05
        ymax2 = sorted(self.deltas)[-1] + 0.05
        if ymax2 < 0.05:
            ymax2 = 0.05
        
        self.axes1.set_xbound(lower=xmin,  upper=xmax )
        self.axes1.set_ybound(lower=ymin1, upper=ymax1)

        self.axes2.set_xbound(lower=xmin,  upper=xmax )
        self.axes2.set_ybound(lower=ymin2, upper=ymax2)
        
        self.axes1.grid(True, color='gray')
        self.plot1.set_xdata(pylab.date2num(self.timesF))
        self.plot1.set_ydata(self.fields)
        
        self.axes2.grid(True, color='gray')
        self.plot2.set_xdata(pylab.date2num(self.timesD))
        self.plot2.set_ydata(self.deltas)
        
        for t in self.strikes1.keys():
            if t < xmin:
                for s in self.strikes1[t]:
                    self.axes1.lines.remove(s)
                del self.strikes1[t]

        for t in self.strikes2.keys():
            if t < xmin:
                for s in self.strikes2[t]:
                    self.axes2.lines.remove(s)
                del self.strikes2[t]
        
        self.canvas1.draw()

        self.canvas2.draw()
        
    def markLightningEvent(self, t):
        """
        Mark a lightning strike in red.
        """
        
        line, = self.axes1.plot([t,t], [-30,30], color='red', linestyle='--')
        try:
            self.strikes1[t].append(line)
        except KeyError:
            self.strikes1[t] = [line,]

        line, = self.axes2.plot([t,t], [-30,30], color='red', linestyle='--')
        try:
            self.strikes2[t].append(line)
        except KeyError:
            self.strikes2[t] = [line,]

    def onExit(self, event):
        """
        Menu point Exit
        """
        
        self.Close()

    def OnClose(self, event):
        """
        Called on application shutdown.
        """
        
        self.stopThread()               #stop reader thread
        self.Destroy()                  #close windows, exit app

    def onSaveAs(self, event):
        """
        Save contents of output window.
        """
        
        filename = None
        dlg = wx.FileDialog(None, "Save Text As...", ".", "", "Text File|*.txt|All Files|*",  wx.SAVE)
        if dlg.ShowModal() ==  wx.ID_OK:
            filename = dlg.GetPath()
        dlg.Destroy()
        
        if filename is not None:
            f = file(filename, 'w')
            text = self.textCtrl.GetValue()
            if type(text) == unicode:
                text = text.encode("latin1")    #hm, is that a good asumption?
            f.write(text)
            f.close()
    
    def onClear(self, event):
        """
        Clear contents of output window.
        """
        
        self.textCtrl.Clear()

    def onSocketRead(self, event):
        """
        Handle input from the serial port.
        """
        
        text = event.data
        
        mtch = dataRE.match(text)
        t = datetime.strptime(mtch.group('date'), "%Y-%m-%d %H:%M:%S.%f")
        if mtch.group('type') == 'FIELD':
            field, junk = mtch.group('data').split(None, 1)
            self.timesF.append(t)
            self.fields.append(float(field))
            
            if len(self.timesF) > self.nKeep:
                self.timesF = self.timesF[1:(self.nKeep+1)]
                self.fields = self.fields[1:(self.nKeep+1)]
            
            #self.drawPlot()
        elif mtch.group('type') == 'DELTA':
            field, junk = mtch.group('data').split(None, 1)
            self.timesD.append(t)
            self.deltas.append(float(field))
            
            if len(self.timesD) > self.nKeep:
                self.timesD = self.timesD[1:(self.nKeep+1)]
                self.deltas = self.deltas[1:(self.nKeep+1)]
            
            self.drawPlot()
        elif mtch.group('type') == 'LIGHTNING':
            self.markLightningEvent(t)
            
            self.textCtrl.AppendText(text+'\n')
        else:
            self.textCtrl.AppendText(text+'\n')

    def SocketThread(self):
        """
        Thread that handles the incomming traffic. Does the basic input 
        transformation (newlines) and generates an SocketRxEvent.
        """
        
        while True:
            try:
                data, addr = self.sock.recvfrom(1024)
                event = SocketRxEvent(self.GetId(), data)
                self.GetEventHandler().AddPendingEvent(event)
            except socket.error as e:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='read data from a spinningCan.py lightning data server and plot it',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
            )
    parser.add_argument('-a', '--address', type=str, default='224.168.2.9',
                        help='mulitcast address to connect to')
    parser.add_argument('-p', '--port', type=int, default=7163,
                        help='multicast port to connect on')
    args = parser.parse_args()
    
    app = wx.App(0)
    frame = EFM100(None, -1, "EFM-100 Lightning Detector", mcastAddr=args.address, mcastPort=args.port)
    app.MainLoop()
    
