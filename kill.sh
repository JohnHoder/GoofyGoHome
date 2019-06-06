#!/bin/bash
#bash script to kill daemons

echo $1

if [ $1 -eq 1 ]; then
	echo "Killing ggh_control_web.py ..."
	ps ax | grep 'ggh_control_web.py' | grep -v grep | awk '{print $1}' | while read line; do
		kill -9 $line
	done;
elif [ $1 -eq 2 ]; then
	echo "Killing ggh_daemon.py ..."
	ps ax | grep 'ggh_daemon.py' | grep -v grep | awk '{print $1}' | while read line; do
		kill -9 $line
	done;
fi

