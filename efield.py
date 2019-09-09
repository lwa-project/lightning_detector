# -*- coding: utf-8 -*-

"""
Module to deal with the messy task of detecting lightning and coming up with a 
range for it.

Used by spinningCan.py, spinningCanTest.py, spinningCanReplay.py, and 
analyzeRecodring.py to make sure they are all on the same page.
"""

import numpy

__version__ = "0.1"
__revision__ = "$Rev$"
__all__ = ['ElectricField', '__version__', '__revision__', '__all__']


class ElectricField(object):
    """
    Class to store and deal with the electric field and its changes.  This class
    will keep up with a moving set of electric field measurments in order to:
    
      1) Keep track of the current field and its derivative, 
      2) Determine if the field is high enough to warrant a warning, and
      3) Determin if lightning has been detected.
      
    This class is designed to take over most if not all of the computations
    needs by spinningCan and its ilk.
    """
    
    def __init__(self, highField=5.0, veryHighField=7.0, minFieldChange=0.04, nKeep=20):
        # Field measurment values
        self.highField = float(highField)
        self.veryHighField = float(veryHighField)
        
        # Lightning detection control values
        self.minFieldChange = float(minFieldChange)
        
        # Field retention control
        self.nKeep = int(nKeep)
        
        # Internal data structures to store the time/field pairs.
        self.times = []
        self.field = []
        
    def updateConfig(self, config):
        """
        Update the current configuration using a dictionary of values.  
        Values looked for are:
        
          * FIELD_AVERAGE - number of seconds to keep and average the
            electric field
          * HIGH_FIELD - field value in kV/m for a high field
          * VERY_HIGH_FIELD - field value in kV/m for a very high field
          * LIGHTNING_MIN_FIELD_CHANGE - minimum field change over 
            ~0.3 s to count as lightning.
            
        All dictionary keys are taken to be upper-cased and are case 
        sensitive.
        """
        
        # Update values
        ## Data retention
        self.nKeep = int(round(20.0*float(config['FIELD_AVERAGE'])))
        if self.nKeep < 7:
            self.nKeep = 7
        
        ## Field control
        self.highField = float(config['HIGH_FIELD'] )
        self.veryHighField = float(config['VERY_HIGH_FIELD'])
        
        ## Lightning control
        self.minFieldChange = float(config['LIGHTNING_MIN_FIELD_CHANGE'])
        
        # Prune
        self.times = self.times[-self.nKeep:]
        self.field = self.field[-self.nKeep:]

    def append(self, time, data):
        """
        Append a new time stamp/electric field value (in kV/m) pair to the
        instance.
        """
        
        try:
            self.times.append(time)
            self.field.append(data)

            self.times = self.times[-self.nKeep:]
            self.field = self.field[-self.nKeep:]
            
            return True
        except:
            return False

    def mean(self):
        """
        Determine the current mean of the electric field and return the value
        in kV/m.
        """
        
        n = 0
        total = 0
        for data in self.field:
            n += 1
            total += data
        
        return total / float(n)

    def __smooth(self, i):
        """
        Perform a simple backwards boxcar smoothing of the data with a window
        of three at the specified location.
        """
        
        n = 1
        smoothData = self.field[i]
        try:
            n += 1
            smoothData += self.field[i-1]
            n += 1
            smoothData += self.field[i-2]
        except IndexError:
            n -= 1

        return smoothData/float(n)

    def deriv(self):
        """
        Compute and return the derivative over a ~0.3 s window (6 samples).
        """
        
        if len(self.field) > 6:
            return self.__smooth(-1) - self.__smooth(-7)
        else:
            return 0.0
            
    def isHigh(self):
        """
        Examine the last field value and determine if we are in a `high field`
        condition or not.
        """
        
        if abs(self.field[-1] ) > self.highField:
            return True
        else:
            return False
            
    def isVeryHigh(self):
        """
        Examine the last field value and determine if we are in a `very high
        field` condition or not.
        """
        
        if abs(self.field[-1] ) > self.veryHighField:
            return True
        else:
            return False

    def isLightning(self):
        """
        Examine the current field list and determine if we have what looks like
        lightning occuring.
        """
        
        deriv = self.deriv()
        if abs(deriv) > self.minFieldChange:
            return True
        else:
            return False
            
    def getLightningDistance(self, miles=False):
        """
        Assuming the lightning is responsible for the field change, estimate
        the distance of the lightning in km (or miles if the `milew` keyword
        is set to True.
        """
        
        deriv = self.deriv()
        dist = (10.0/abs(deriv))**(1/3.) * 5
        
        if miles:
            return dist*0.621371192
        else:
            return dist
    
