# Goofy Go Home

GoofyGoHome is software for a prophylactic real-time logfile analysis and a consequent threat detection apparent therein. The software is to concentre particularly on network services, respectively, on the log files thereof, on Linux platform. The log files are observed for potential security breach attempts in regard to respective service as defined in the configuration file. It purports to reach the largest extent of versatility possible for a straightforward configuration of new services which are to be monitored and protected by the software. An important asset of GoofyGoHome is a web-based interface accessible through HTTP protocol which allows the software to be administered remotely with ease.

## How to use

First configure the observed journal files (log files) in the config file

	vi conf.conf

Once your desired configuration is set up, run the daemon

	python ggh_daemon.py --start

From now on, the services you specified in the config file are observed for the potential attacks as defined in the config file.

If you wish to administer the daemon from web interface, run the web server with command

	python ggh_control_web.py

This will run the web service by default on port 8008.

To control the daemon from terminal, you can use CLI tool as follows:

	python ggh_control_cli.py

