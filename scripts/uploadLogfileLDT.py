#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import os
import sys
import time
import requests
from socket import gethostname


URL = "https://lda10g.unm.edu/metadata/sorter/index.py"
KEY = "c0843461abe746a4608dd9c897f9b261"
SITE = gethostname().split('-', 1)[0]
TYPE = "SSLOG"

# Send the update to lwalab
r = os.path.realpath(sys.argv[1])
f = requests.post(URL,
                  data={'key': KEY, 'site': SITE, 'type': TYPE, 'subsystem': 'LDT'},
                  files={'file': open(r, 'rb')},
                  verify=False) # We don't have a certiticate for lda10g.unm.edu
print(f.text)
f.close()
