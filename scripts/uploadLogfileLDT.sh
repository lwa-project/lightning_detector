#!/bin/bash

ls /lwa/LightningDetector/logs/*.gz | xargs -n1 /lwa/LightningDetector/scripts/uploadLogfileLDT.py
