#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import json
import re
import pickle
import socket

from run_command import Utils
from database import Database
#from rule_executor import DbWatcher
import constants

END_SELF = ">>>"

class CommandProcessor(object):
	
	def __init__(self, daemonInstance, dbWatcher):
		self.daemonInstance = daemonInstance
		self.dbWatcher = dbWatcher
		self.db = Database()
		#print(self.dbWatcher)
		pass

	def proceed(self, command):
		ret = self.__commandHandler(command.decode("utf-8"))
		return ret
	
	def __commandHandler(self, command):
		if command == "help":
			commandlist = {"Command list" : {
			"help" : "Show this help, how the client is to be used and a list of available commands",
			"version" : "Show version of GGH",
			"db events show [json]" : "Show events stored in events table with planned antiaction",
			"db events check" : "Check for (time) validity of detected events in database",
			"db events release ID" : "Removes event with a corresponding ID and, if applicable, performs the \"antiaction\"",
			"db events reset" : "Reset events table, all events with planned antiaction will be lost",
			"db eventlog show [json]" : "Show detected events stored in database",
			"db eventlog remove ID" : "Removes event with a corresponding ID from eventlog table",
			"daemon stop" : "Stop GGH daemon",
			}}
			return json.dumps(commandlist) + END_SELF


		# Leaving it here for debugging purposes
		if command == "ping":
			return "pong" + END_SELF

		if command == "version":
			return constants.version + END_SELF

		if command == "daemon stop":
			# Kill the daemon
			self.daemonInstance.stop()
			return "Shutting daemon down ..." + END_SELF

		if command == "db events check":
			self.db.checkLifeOfEvents()
			#self.dbWatcher.onThread(self.dbWatcher.checkEventsNow)
			#self.dbWatcher.start()
			return "Validity of all events in database has been checked." + END_SELF

		if command == "db eventlog show":
			ret = self.db.getAllEventlog()
			return ret + END_SELF

		if command == "db eventlog show json":
			ret = self.db.getAllEventlogJSON()
			return ret + END_SELF

		if command == "db events show":
			#self.dbWatcher.onThread(self.dbWatcher.checkEventsNow, self.db)
			#self.dbWatcher.start()
			ret = self.db.getAllEvents()
			return ret + END_SELF

		if command == "db events show json":
			ret = self.db.getAllEventsJSON()
			return ret + END_SELF

		if command == "db events reset":
			ret = self.db.resetEvents()
			if ret is False:
				return "Databse has been reset" + END_SELF
			else:
				return "Some error occured" + END_SELF

		if re.match(r'^db events release', command):
			match = re.search('(?<=db events release )\d+$', command)
			if match != None:
				idx = match.group()
				antiaction = self.db.getAntiactionByID(idx)
				Utils.execute_action(antiaction)
				self.db.removeEventByID(idx)
			else:
				return "Event ID not found." + END_SELF
			return "Event with ID {} has been released and restored.".format(idx) + END_SELF

		if re.match(r'^db eventlog remove', command):
			match = re.search('(?<=db eventlog remove )\d+$', command)
			if match != None:
				idx = match.group()
				self.db.removeEventlogByID(idx)
			else:
				return "Event ID not found." + END_SELF
			return "Event with ID {} has been removed.".format(idx) + END_SELF

		if re.match(r'^dnslookup', command):
			match = re.search('(?<=dnslookup ).*?$', command)
			if match != None:
				ip = match.group()
				try:
					name,alias,addresslist = socket.gethostbyaddr(ip)
				except socket.herror:
					#reversed_dns[0]
					name, alias, addresslist = None, None, None
					return "Not found" + END_SELF
					pass
				print(name,alias,addresslist)
			else:
				return "50m37h1ng w3n7 wr0ng." + END_SELF
			return "{}".format(name) + END_SELF

		# if ENTER was pressed
		if command == "":
			return END_SELF

		# Command is not any of the above
		else:
			return "Command not found.\n" + END_SELF
			#return "Command not found.\nReceived: \"" + command + "\"" + END_SELF
		command = ""