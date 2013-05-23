#!/bin/bash 
if [ -z "$1" ]; then
	echo "You must supply the name of a script. This script must be in the working directory, and must not rely on other scripts or executables without explicitly supplying a path. The script will be copied to the /etc/init.d/ folder, and will be scheduled to start in runlevels 2,3,4,5."
else
	sudo cp $1 /etc/init.d/$1
	sudo update-rc.d $1 defaults 99 
	# defaults means runlevels 2345, not 016
	# 99 is the order, in this case meaning after everything else of 
	# interest
fi