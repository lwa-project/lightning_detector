#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Graphical interface to the lightning data served up by spinningCan.py.

$Rev$
$LastChangedBy$
$LastChangedDate$
"""

import sys
import time
import getopt
import socket

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
		vbox = wx.BoxSizer(wx.VERTICAL)
		self.figure = Figure((4.0, 4.0), dpi=100)
		self.canvas = FigureCanvasWxAgg(self, -1, self.figure)
		#panel.SetSizer(vbox)
		vbox.Add(self.canvas, 1, wx.EXPAND)
		
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

		self.axes = self.figure.gca()
		self.axes.set_axis_bgcolor('white')
		self.figure.subplots_adjust(left=0.25)
		
		pylab.setp(self.axes.get_xticklabels(), fontsize=8)
		pylab.setp(self.axes.get_yticklabels(), fontsize=8)

		# plot the data as a line series, and save the reference 
		# to the plotted line series
		#
		self.plot1 = self.axes.plot([2,], [0,], linewidth=1, color='green')[0]
		self.plot2 = self.axes.plot([2,], [0,], linewidth=1, color='blue', linestyle=':')[0]

		self.axes.set_xlabel('Time')
		self.axes.set_ylabel('E-Field [kV/m]')
		self.axes.xaxis.set_major_locator(LinearLocator(numticks=6))
		self.axes.xaxis.set_major_formatter(DateFormatter("%H:%M:%S"))
		self.figure.autofmt_xdate()
		
		self.canvas.draw()
		
	def drawPlot(self):
		"""
		Draw the plot.
		"""
		
		xmin = self.timesF[0]
		xmax = self.timesF[-1]
		
		ymin = sorted(self.fields)[0]
		if ymin > -0.05:
			ymin = -0.05
		ymax = sorted(self.fields)[-1]
		
		self.axes.set_xbound(lower=xmin, upper=xmax)
		self.axes.set_ybound(lower=ymin, upper=ymax)
		
		self.axes.grid(True, color='gray')
		self.plot1.set_xdata(pylab.date2num(self.timesF))
		self.plot1.set_ydata(self.fields)
		
		self.plot2.set_xdata(pylab.date2num(self.timesD))
		self.plot2.set_ydata(self.deltas)
		
		self.canvas.draw()
		
	def markLightningEvent(self, t):
		"""
		Mark a lightning strike in red.
		"""
		
		self.plot1.vlines(t, -30, 30, color='ref', linestyle='--')

	def onExit(self, event):
		"""
		Menu point Exit
		"""
		
		self.Close()

	def OnClose(self, event):
		"""
		Called on application shutdown.
		"""
		
		self.StopThread()               #stop reader thread
		self.serial.close()             #cleanup
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
		t = datetime.strptime(mtch.group('date'), "%Y-%m-%d %H:%M:%S")
		if mtch.group('type') == 'FIELD':
			field, junk = mtch.group('data').split(None, 1)
			self.timesF.append(t)
			self.fields.append(float(field))
			
			if len(self.timesF) > 180:
				self.timesF = self.timesF[1:]
				self.fields = self.fields[1:]
			
			#self.drawPlot()
		elif mtch.group('type') == 'DELTA':
			field, junk = mtch.group('data').split(None, 1)
			self.timesD.append(t)
			self.deltas.append(float(field))
			
			if len(self.timesD) > 180:
				self.timesD = self.timesD[1:]
				self.deltas = self.deltas[1:]
			
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
			except socket.error, e:
				pass


def usage(exitCode=None):
	print """spinningCanGUI.py - Read data from a spinningCan.py lightning data 
server and plot it.

Usage: spinningCanGUI.py [OPTIONS]

Options:
-h, --help                  Display this help information
-a, --address               Mulitcast address to connect to (default = 224.168.2.9)
-p, --port                  Multicast port to connect on (default = 7163)
"""

	if exitCode is not None:
		sys.exit(exitCode)
	else:
		return True


def parseOptions(args):
	config = {}
	config['addr'] = "224.168.2.9"
	config['port'] = 7163

	try:
		opts, args = getopt.getopt(args, "ha:p:", ["help", "address=", "port="])
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
		else:
			assert False
	
	# Add in arguments
	config['args'] = args

	# Return configuration
	return config


if __name__ == "__main__":
	config = parseOptions(sys.argv[1:])

	app = wx.App(0)
	frame = EFM100(None, -1, "EFM-100 Lightning Detector", mcastAddr=config['addr'], mcastPort=config['port'])
	app.MainLoop()

