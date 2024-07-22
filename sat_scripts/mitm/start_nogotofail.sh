#!/bin/sh
python -m nogotofail.mitm --mode redirect -A selfsigned -p 0.4 -q  2>&1 | tee ./mitmlog.txt  
