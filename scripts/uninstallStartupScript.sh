#!/bin/bash 
if [ -z "$1" ]; then
	echo "You must supply the name of a script. The script must already have been installed in /etc/init.d. Be warned that this script makes no checks on what is being removed, aside from it being there."
else
	sudo update-rc.d $1 remove
	sudo rm /etc/init.d/$1
fi