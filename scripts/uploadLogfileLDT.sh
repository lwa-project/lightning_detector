#!/bin/bash

ls /lwa/LightningDetector/logs/*.gz | xargs -n1 ~ops/uploadLogfileLDT.py

