#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import sys
import json
import os
from collections import OrderedDict
import sqlite3

try:
	from prettytable import PrettyTable
except ImportError:
    sys.stderr.write("Missing `prettytable` package: pip3 install prettytable\n")
    sys.exit(1)

from run_command import Utils

table_eventlog = """
				CREATE TABLE IF NOT EXISTS eventlog (
				id INTEGER NOT NULL,
				"belongService" TEXT,
				"comesFromRule" TEXT,
				distingueur TEXT,
				"timeOfEvent" TEXT,
				PRIMARY KEY (id)
				)
				"""

table_events = """
				CREATE TABLE IF NOT EXISTS events (
				id INTEGER NOT NULL,
				"belongService" TEXT,
				"comesFromRule" TEXT,
				distingueur TEXT,
				"timeOfEvent" TEXT,
				"eventExp" INTEGER,
				antiaction TEXT,
				PRIMARY KEY (id)
				)
				"""

class Database(object):
	def __init__(self):
		self._datadir = os.path.dirname(os.path.realpath(__file__)) + '/' + 'data/'
		try:
			self._db = sqlite3.connect('{}{}'.format(self._datadir, 'database.db'), check_same_thread=False)
		except sqlite3.OperationalError as e:
			print("ERROR: Database connection failed ~ {}".format(e))
			sys.exit(1)
			pass
		self.cur = self._db.cursor()
		self.cur.execute(table_eventlog)
		self.cur.execute(table_events)

		self.eventlog = "eventlog"
		self.events = "events"
		pass

	def close(self):
		self._db.close()

	# Methods for eventlog table
	# Time info is saved in time.asctime() format
	def addEventlog(self, belongService, comesFromRule, distingueur, timeOfEvent):
		self.cur.execute("INSERT INTO {}(belongService, comesFromRule, distingueur, timeOfEvent) VALUES(?, ?, ?, ?)"
			.format(self.eventlog),(belongService, comesFromRule, distingueur, timeOfEvent))
		self._db.commit()

	def removeEventlogByID(self, id):
		res = self.cur.execute("DELETE FROM {} WHERE id LIKE (?)".format(self.eventlog), id)
		self._db.commit()

	def getAllEventlog(self):
		result = self.cur.execute('SELECT * FROM {}'.format(self.eventlog))
		# Use PrettyTable library for a neat table format
		x = PrettyTable()
		x.field_names = ["[ID]", "[Service]", "[Rule]", "[Distingueur]", "[Jailed]"]
		for row in result:
			x.add_row([row[0],row[1],row[2],row[3],row[4]])
		return str(x)

	def getAllEventlogJSON(self):
		result = self.cur.execute('SELECT * FROM {}'.format(self.eventlog))
		items = [dict(zip([key[0] for key in self.cur.description], row)) for row in result]
		return json.dumps({'eventlog' : items})

	def resetEventlog(self):
		res = self.cur.execute("DELETE FROM {}".format(self.eventlog))
		self._db.commit()
		return res

	# Methods for events table
	# Time info is saved in time.asctime() format
	def addEvent(self, belongService, comesFromRule, distingueur, timeOfEvent, eventExp, antiaction):
		self.cur.execute("INSERT INTO {}(belongService, comesFromRule, distingueur, timeOfEvent, eventExp, antiaction) VALUES(?, ?, ?, ?, ?, ?)"
			.format(self.events),(belongService, comesFromRule, distingueur, timeOfEvent, eventExp, antiaction))
		self._db.commit()

	def getEventsByService(self, belongService):
		events = self.cur.execute("SELECT * FROM {} WHERE belongService LIKE ?".format(events), (belongService))
		return events

	def getAllEvents(self):
		result = self.cur.execute('SELECT * FROM {}'.format(self.events))
		# Use PrettyTable library for a neat table format
		x = PrettyTable()
		x.field_names = ["[ID]", "[Service]", "[Rule]", "[Distingueur]", "[Jailed]", "[Expiration]", "[Antiaction]"]
		for row in result:
			x.add_row([row[0],row[1],row[2],row[3],row[4],row[5],row[6]])
		return str(x)

	def getAllEventsJSON(self):
		result = self.cur.execute('SELECT * FROM {}'.format(self.events))
		items = [dict(zip([key[0] for key in self.cur.description], row)) for row in result]
		return json.dumps({'events' : items})
			
	def removeEventByID(self, id):
		res = self.cur.execute("DELETE FROM {} WHERE id LIKE ?".format(self.events), (id,))
		self._db.commit()

	def getAntiactionByID(self, id):
		result = self.cur.execute("SELECT antiaction FROM events WHERE id LIKE {}".format(id))
		for row in result:
			# return first match, we expect that ID is unique
			return row[0]

	def checkDistingueurDetectedForRule(self, distingueur, rulename):
		result = self.cur.execute("SELECT id, comesFromRule, distingueur FROM events WHERE distingueur LIKE '{}' AND comesFromRule LIKE '{}'".format(distingueur, rulename))
		ruledict = {}
		for row in result:
			ruledict.update({row[1]:distingueur})
			for key,val in ruledict.items():
				print("{} -> {}".format(key, val))
				if row[1] == key and distingueur == val:
					return True
			print(row)
		print(ruledict)
		return False

	def resetEvents(self):
		res = self.cur.execute("DELETE FROM {}".format(self.events))
		self._db.commit()
		return res


	# Go through all of the events and check whether they should be deleted already based on eventExp
	def checkLifeOfEvents(self):
		result = self.cur.execute('SELECT timeOfEvent,eventExp,id,antiaction FROM {}'.format(self.events))
		for row in result:
			eventTime = int(time.mktime(time.strptime(row[0])))
			if eventTime+row[1] <= int(time.time()):
				# execute antiaction and delete the entry
				print("Event with ID {} has expired and will be released.".format(row[2]))
				Utils.execute_action(row[3])
				self.removeEventByID(row[2])
				self._db.commit()
