#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import time
from socket import gethostname
import urllib, urllib2, MultipartPostHandler 


URL = "https://lda10g.alliance.unm.edu/metadata/sorter/index.py"
KEY = "c0843461abe746a4608dd9c897f9b261"
SITE = gethostname().split('-', 1)[0]
TYPE = "SSLOG"

# Send the update to lwalab
p = urllib2.build_opener(MultipartPostHandler.MultipartPostHandler())
r = os.path.realpath(sys.argv[1])
f = p.open(URL, data={'key': KEY, 'site': SITE, 'type': TYPE, 'subsystem': 'LDT', 'file': open(r)})
print f.read()
f.close()

