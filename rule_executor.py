#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import time
import threading
import ipaddress
from threading import Thread
import queue
import select

try:
	from systemd import journal
except ImportError:
    sys.stderr.write("Missing `systemd` package: pip install systemd\n")
    sys.exit(1)

from config import Prefs, Service, Rule, ServicesManager
from run_command import Utils
from filetracker import FileTracker
from database import Database


class DbWatcher(Thread):
	def __init__(self, q = queue.Queue(10), loop_time = 1.0/60):
		print("DB Watcher initialized")
		super(DbWatcher, self).__init__()
		self.name = "DB Watcher"
		self.q = q
		self.db = Database()
		self.timeout = loop_time
		# Get DB_EVENT_CHECK_SLEEP value from config file
		self._sleeptime = Prefs().getGeneralPref('DB_EVENT_CHECK_SLEEP')
		self.isTimed = False
		pass

	def onThread(self, function, *args, **kwargs):
		self.q.put((function, args, kwargs))

	def run(self):

		while True:
			try:
				function, args, kwargs = self.q.get(timeout=self.timeout)
				function(*args, **kwargs)
				print(self.q)

			except queue.Empty:
				if self.isTimed == False:
					self.isTimed = True
					timerThread = threading.Timer(self._sleeptime, self.helperThreadSetIsTimed)
					timerThread.setName("DbWatcher Timer")
					timerThread.start()

					self.checkEventsNow()
				pass

	def checkEventsNow(self):
		print("[DbWatcher] Checking events validity ...")
		self.db.checkLifeOfEvents()
		pass

	def helperThreadSetIsTimed(self):
		self.isTimed = False


class RuleExecutor(object):
	def __init__(self, prefs = None):
		self._prefs = prefs
		self.db = Database()
		self.threadNames = []

		for service in ServicesManager().getAllServices():
			crnt_rules = []
			for rule in service.getRules():
				# set ServiceName, we need this for the DB and journald search method
				rule.setNameOfBelongService(service.getName())
				# strip first and last double quote
				if rule.getRegex().startswith('"') and rule.getRegex().endswith('"'):
					rule.setRegex(str(rule.getRegex())[1:-1])
					# replacable with re.sub(r'^"|"$', '', rule.getRegex()) --- performance???
				#print rule.getId()
				#print(service.getName() + ": " + str(rule.getRulename()))
				if (rule.getEnabled()).lower() == "true":
					crnt_rules.append(rule)

			
			logfile = service.getLogfile()
			#print("LOGFILE -> {}".format(logfile))
			if logfile == None or logfile == "":
				continue

			elif logfile != "journald":
				if crnt_rules != []:
					self.execute_search(logfile=logfile, rules_list=crnt_rules, rtrctv=service.getRetroactive())

			elif logfile == "journald":
				self.threadNames = [t.getName() for t in threading.enumerate()]
				#print(self.threadNames)

				if service.getName() not in self.threadNames:
					#print("Thread {} is not in the list yet.".format(service.getName()))
					if crnt_rules != []:
						# start Journald watcher thread
						jd_thread = Journald_watcher(name=service.getName(), rule_list=crnt_rules, retroactive=service.getRetroactive())
						jd_thread.start()
				pass
		pass

	# Takes care for rule application and enforcement on "classical" log files
	def execute_search(self, logfile, rules_list, rtrctv):

		file_tracker = FileTracker(logfile, rtrctv)
		last_offset = file_tracker.get_offset()
		tmp_offset = last_offset
		#print("LAST OFFSET -> {}".format(last_offset))

		# there are new entries in the logfile
		if last_offset is not None:
			print("Processing log file [{}] from offset [{}]".format(logfile, last_offset))

			fp = None

			try:
				if logfile.startswith('/'):
					fp = open(logfile, "r")
				else:
					relpath = os.path.dirname(os.path.realpath(__file__)) + '/' + logfile
					fp = open(relpath, "r")

				fp.seek(last_offset)
			except IOError:
				print("File pointer not obtained. ~Return")
				return
				pass

			# Play the rules
			for rule in rules_list:
				regexyolo = re.compile(rule.getRegex())
				#print(service.getName() + ": " + str(rule.getName()))
				threshold_count = rule.getThresholdCount() if rule.getThresholdCount() != None else self.prefs.getGeneralPref('THRESHOLDCOUNT')

				for line in fp:
					line = line.strip()
					r1 = regexyolo.search(line)
					if r1 is not None:
						#print "yes"
						try:
							ipaddr = r1.group(rule.getCriteriaToDistinguish())
							#print(ipaddr)
							# Check if detected event is not apriori enabled in HOSTS_ALLOW
							if checkIPenabled(ipaddr) == 1:
								continue
							
							dictx = rule.getIpXoccurDict()
							ipcnt = dictx.get(ipaddr, 0) # 0 is the default value if key does not exist
							#print("ipaddr {} / {}".format(ipaddr, ipcnt))items
							rule.updateIpXoccur(ipaddr, ipcnt + 1)
						except:
							pass

				if self.is_last(rule, rules_list) == False:
					print("rules_list has more, seeking back to last_offset")
					fp.seek(last_offset)

				tempAction = rule.getAction()
				tempAntiaction = rule.getAntiaction()
				for element, cnt in rule.getIpXoccurDict().items():
					# IP is in HOSTS_DENY or THRESHOLD value has been exceeded
					if checkIPenabled(element) == 0 or cnt >= int(threshold_count):
						#print("Threshold count -> {}".format(threshold_count))
						#print("OccurenceCount after this read -> {}".format(cnt))
						
						# Replace CRITERIA_TO_DISTINGUISH group placeholder in Regex
						if tempAction != None:
							replaced1 = re.sub(rule.getCriteriaToDistinguish(), str(element), tempAction)
							rule.setAction(replaced1)

							# check if such a tuple (rule,distingueur) is already in database
							# if it is, we do not want to apply ACTION and ANTIACTION again
							# nor we want to log this event to events table, only eventlog
							if self._prefs.getGeneralPref('DO_NOT_DUPLICATE').lower() == 'true':
								if self.db.checkDistingueurDetectedForRule(element, rule.getRulename()) == False:
									# Run the action, let it roll baby
									print("Executing ACTION -> {}".format(rule.getAction()))
									Utils.execute_action(rule.getAction())
								else:
									print("DO_NOT_DUPLICATE is ON -> skipping ACTION")
							else:
								# Run the action, let it roll baby
								print("Executing ACTION -> {}".format(rule.getAction()))
								Utils.execute_action(rule.getAction())

						if tempAntiaction != None:
							replaced2 = re.sub(rule.getCriteriaToDistinguish(), str(element), tempAntiaction)
							rule.setAntiaction(replaced2)

							#print(rule.getAntiaction())

						if self._prefs.getGeneralPref('DO_NOT_DUPLICATE').lower() == 'true':
							if self.db.checkDistingueurDetectedForRule(element, rule.getRulename()) == False:
								# Add event to DB
								if rule.getAntiaction() != None:
									self.db.addEvent(rule.getNameOfBelongService(), rule.getRulename(), element, time.asctime(), 
										rule.getJailtime() if rule.getJailtime() != None else self._prefs.getGeneralPref('JAILTIME'), rule.getAntiaction())
							else:
								print("DO_NOT_DUPLICATE is ON -> skipping DB store to events.")

						self.db.addEventlog(rule.getNameOfBelongService(), rule.getRulename(), element, time.asctime())

						# We imposed a sanction, now we reset the counter
						rule.updateIpXoccur(element, 0)


				print("{}: IP X OCCUR DICT -> {}".format(rule.getRulename(), rule.getIpXoccurDict()))


			last_offset = fp.tell()
			#print(last_offset)
			fp.close()

			if last_offset != tmp_offset:
				file_tracker.save_offset(last_offset)
				tmp_offset = last_offset
			else:
				print("Log file size has not changed. Nothing to do.")

	# Way to check if the rule is the last one in the particular service to be applied
	def is_last(self, rule, rules_list):
		curr_index = rules_list.index(rule)
		#print("CURR = {} at position {}".format(rules_list[curr_index].getRulename(), curr_index))
		try:
			next = rules_list[curr_index+1]
			#print("NEXT = {} at position {}".format(next.getRulename(), curr_index+1))
			return False
		except IndexError:
			#print("OUT OF INDEX, return True, we are the last one")
			next = None
			return True
		return


class Journald_watcher(Thread):
	def __init__(self, rule_list, name = "", retroactive = False, q = queue.Queue(10), loop_time = 1.0/60):
		print("Journald watcher [{}] initialized".format(name))
		super(Journald_watcher, self).__init__()
		self._prefs = Prefs()
		self.db = Database()
		self.name = name
		self.q = q
		self.rules = rule_list
		#print(self.rules)
		self.retroactive = retroactive

		self.j = journal.Reader()
		self.j.log_level(journal.LOG_INFO)
		try:
			self.j.add_match(_SYSTEMD_UNIT="{}.service".format(rule_list[0].getNameOfBelongService()))
		except:
			return
		if self.retroactive == False:
			self.j.seek_tail()
		self.j.get_previous()
		pass

	def run(self):
		#rule = None
		if self.rules == [] or self.rules == None:
			return

		#for rule in self.rules:
			#print(rule)
			#break
			#print("Journald_watcher.run -> {}".format(rule.getRulename()))

		#print("Processing {}".format(rule.getNameOfBelongService()))

		p = select.poll()
		p.register(self.j, self.j.get_events())

		if self.retroactive == True:
			# Send a message to journald to generate a I/O traffic
			# so that poll catches events in the past without having
			# to wait for journal.APPEND to occur naturally.
			journal.send("GGH")

		# Inspiration taken from https://yalis.fr/git/yves/pyruse/src/branch/master/pyruse/main.py
		# In accordance with § 31 odst. 1 písm. a) zákona č. 121/2000 Sb., autorský zákon
		while p.poll():
			#print(self.j.process())
			if self.j.process() != journal.APPEND:
				continue
			for entry in self.j:
				if entry['MESSAGE'] != "":
					# Print SYSTEMD messages for debugging
					#print(str(entry['__REALTIME_TIMESTAMP'])+ ' ' + entry['MESSAGE'])
					#print()
					for rule in self.rules:
						self.processRule(rule, entry['MESSAGE'])
		pass

	def processRule(self, rule, message):
		#print("{} - Processing the message for the rule {} ...".format(self.name, rule.getRulename()))
		regexyolo = re.compile(rule.getRegex())
		r1 = regexyolo.search(message)
		if r1 is not None:
			print("Rule {} -> {} triggered".format(rule.getNameOfBelongService(), rule.getRulename()))
			try:
				ipaddr = r1.group(rule.getCriteriaToDistinguish())
				if checkIPenabled(ipaddr) == 1:
					return
				dictx = rule.getIpXoccurDict()
				ipcnt = dictx.get(ipaddr, 0) # 0 is the default value if key does not exist
				#print("ipaddr {} / {}".format(ipaddr, ipcnt))
				rule.updateIpXoccur(ipaddr, ipcnt + 1)

			except:
				pass

			# Sanction maybe?
			self.sanctionner(rule)

	def sanctionner(self, rule):
		threshold_count = rule.getThresholdCount() if rule.getThresholdCount() != None else self._prefs.getGeneralPref('THRESHOLDCOUNT')
		tempAction = rule.getAction()
		tempAntiaction = rule.getAntiaction()
		for element, cnt in rule.getIpXoccurDict().items():
			if checkIPenabled(element) == 0 or cnt >= int(threshold_count):
				#print("Threshold count -> {}".format(threshold_count))
				#print("OccurenceCount after this read -> {}".format(cnt))

				# Replace CRITERIA_TO_DISTINGUISH group placeholder in Regex
				if tempAction != None:
					replaced1 = re.sub(rule.getCriteriaToDistinguish(), str(element), tempAction)
					rule.setAction(replaced1)

					# check if such a tuple (rule,distingueur) is already in database
					# if it is, we do not want to apply ACTION and ANTIACTION again
					# nor we want to log this event to events table, only eventlog
					if self._prefs.getGeneralPref('DO_NOT_DUPLICATE').lower() == 'true':
						if self.db.checkDistingueurDetectedForRule(element, rule.getRulename()) == False:
							# Run the action, let it roll baby
							print("FIRST TIME")
							print("Executing ACTION -> {}".format(rule.getAction()))
							Utils.execute_action(rule.getAction())
						else:
							print("DO_NOT_DUPLICATE is ON -> skipping ACTION")
					else:
						# Run the action, let it roll baby
						print("Executing ACTION -> {}".format(rule.getAction()))
						Utils.execute_action(rule.getAction())

				if tempAntiaction != None:
					replaced2 = re.sub(rule.getCriteriaToDistinguish(), str(element), tempAntiaction)
					rule.setAntiaction(replaced2)

				#print(rule.getAntiaction())

				# Add event to DB
				# Here is important if Antiaction is set. If that is the case, the event is added both to events and eventlog tables
				# In events table are stored only events with antiaction
				if self._prefs.getGeneralPref('DO_NOT_DUPLICATE').lower() == 'true':
					if self.db.checkDistingueurDetectedForRule(element, rule.getRulename()) == False:
						print("FIRST TIME")
						# Add event to DB events table
						if rule.getAntiaction() != None:
							self.db.addEvent(rule.getNameOfBelongService(), rule.getRulename(), element, time.asctime(), 
								rule.getJailtime() if rule.getJailtime() != None else self._prefs.getGeneralPref('JAILTIME'), rule.getAntiaction())
					else:
						print("DO_NOT_DUPLICATE is ON -> skipping DB store to events.")

				# Add event to DB eventlog table
				self.db.addEventlog(rule.getNameOfBelongService(), rule.getRulename(), element, time.asctime())

				# We imposed the sanction, now we reset the counter
				# Die Strafe wird getilgt, nehehe
				rule.updateIpXoccur(element, 0)

		print("{} : OCCURCNT DICT -> {}".format(rule.getRulename(), rule.getIpXoccurDict()))

# returns 0 if denied
# returns 1 if allowed
# returns 2 if ip is not within the scope of any apriori rule
def checkIPenabled(ip):
	_prefs = Prefs()
	_deny = _prefs.getGeneralPref('HOSTS_DENY').split(",")
	_allow = _prefs.getGeneralPref('HOSTS_ALLOW').split(",")

	# HOSTS_ALLOW is privileged to HOSTS_DENY
	for net in _allow:
		if ipaddress.ip_address(ip) in ipaddress.ip_network(net):
			#print("IP apriori allowed -> {}".format(ip))
			return 1

	for net in _deny:
		if ipaddress.ip_address(ip) in ipaddress.ip_network(net):
			#print("IP apriori denied -> {}".format(ip))
			return 0

	return 2
