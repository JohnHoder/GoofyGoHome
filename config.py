#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import time

class Prefs():
	# Keep instance reference
	_singletonInstance = None
	_configFile = None

	def __new__(cls, *args, **kwargs):
		if not cls._singletonInstance:
			# Create instance
			cls._singletonInstance = super(Prefs, cls).__new__(Prefs) # object
			pass
		# Return the instance
		return cls._singletonInstance

	def __init__(self, configFile=None):
		if configFile == None:
			return

		self.load_prefs(configFile)
		pass

	@staticmethod
	def getInstance():
		return Prefs._singletonInstance

	# The calculate_seconds function is taken from https://github.com/denyhosts/denyhosts/blob/master/DenyHosts/util.py
	# In accordance with § 31 zákona č. 121/2000 Sb., autorský zákon
	def calculate_seconds(self, timestr, zero_ok=False):

		TIME_CONV_TABLE = {
		's' : 1,
		'm' : 60,
		'h' : 3600,
		'd' : 86400,
		'w' : 604800,
		'y' : 3153600
		}

		TIME_SPEC_REGEX = re.compile(r"""(?P<units>\d*)\s*(?P<period>[smhdwy])?""")

		# return the number of seconds in a given timestr such as 1d (1 day),
		# 13w (13 weeks), 5s (5seconds), etc...

		# Avoid potential load recursions
		if type(timestr) is int:
			return timestr

		m = TIME_SPEC_REGEX.search(timestr)
		if not m:
			raise Exception("Invalid time specification: string format error: %s", timestr)

		units = int(m.group('units'))
		period = m.group('period') or 's' # seconds is the default

		if units == 0 and not zero_ok:
			raise Exception("Invalid time specification: units = 0")

		seconds = units * TIME_CONV_TABLE[period]
		return seconds
		

	def load_prefs(self, confFile):
		PREFS_REGEX = re.compile(r"""(?P<name>.*?)\s*[:=]\s*(?P<value>.*)""")
		SERVICE_REGEX = re.compile(r"""\[(?P<service>.*?)\]""")
		TIME_REGEX = re.compile(r"""(?P<data>\d*[smhdwy])""")

		RULE_REGEX = re.compile(r"""(?P<ruleid>\d+)_(?P<prefname>\D+)""")
		LOGPREF_REGEX = re.compile(r"""(?P<prefname>LOG_LOCATION).*""")

		try:
			fp = open(confFile, "r")

			servicesManager = ServicesManager()

			for line in fp:
				line = line.strip()

				# Ignore comments and empty lines
				if not line or line[0] in ('\n', '#'):
					continue

				try:
					n = SERVICE_REGEX.match(line) #match searches only at the begining of the line
					if n is not None:
						serviceName = n.group('service')
						#print(serviceName)

						service = servicesManager.addService(Service(serviceName))

					else:
						m = PREFS_REGEX.search(line)
						if m is not None:
							name = m.group('name').upper()
							value = m.group('value')

							# process LOG_LOCATION pref
							if name == "LOG_LOCATION":
								service.addLogfile(value)
							elif name == "RETROACTIVE":
								service.setRetroactive(value)

							#calculate seconds
							t = TIME_REGEX.match(value)
							if t is not None:
								# convert time values to seconds
								value = self.calculate_seconds(t.group('data'))
								#print(value)

							#print("{}, {}").format(name, value)

							if not value:
								value = None

							(servicesManager.getServiceByName(serviceName)).addPref({name:value})

				except Exception as e:
					pass
		except Exception as e:
			pass

		# refresh logfile location variable


		# load Rules to their place
		for service in ServicesManager().getAllServices():
			for prefName in service.getPrefs().keys():
				#print(prefName)
				#if 
				n = RULE_REGEX.match(prefName) #match searches only at the begining of the line
				if n is not None:
					#print "found"
					pref = n.group('prefname')
					ruleid = n.group('ruleid')
					#print ruleid
					#print pref
					val = service.getPrefs()[prefName]
					rule = service.addRule(Rule(id=ruleid))

					#print("{} -> {} -> {}").format(ruleid, pref, val)

					if pref == "RULENAME":
						rule.setRulename(val)
					elif pref == "ENABLED":
						rule.setEnabled(val)
					elif pref == "CRITERIA_TO_DISTINGUISH":
						rule.setCriteriaToDistinguish(val)
					elif pref == "REGEX":
						rule.setRegex(val)
					elif pref == "THRESHOLDCOUNT":
						rule.setThresholdCount(val)
					elif pref == "ACTION":
						rule.setAction(val)
					elif pref == "ANTIACTION":
						rule.setAntiaction(val)
					elif pref == "JAILTIME":
						rule.setJailtime(val)

	def getGeneralPref(self, prefName):
		generalServ = ServicesManager().getServiceByName("general")
		generalPrefs = generalServ.getPrefs()
		return generalPrefs[prefName]


		#self.general.getPref()
		#print servicesManager.getAllServicesNames()
		#print servicesManager.getServiceByName("test").getPrefs()
		#print servicesManager.getServiceByName("test").getNoOfRules()
		#print servicesManager.dumpPrefs()


class Rule(object):
	def __init__(self, id, logfile = None, rulename = None, enabled = False, criteria_to_distinguish = None, regex = None, thresholdCount = None, action = None, antiaction = None, jailtime = None):
		self._id = id
		#self._logfile = logfile
		self._rulename = rulename
		self._enabled = enabled
		self._criteria_to_distinguish = criteria_to_distinguish
		self._regex = regex
		self._thresholdCount = thresholdCount
		self._action = action
		self._antiaction = antiaction
		self._jailtime = jailtime

		self._nameOfBelongService = None

		self._ip_x_occur_dict = dict()

	def getId(self):
		return self._id

	def getNameOfBelongService(self):
		return self._nameOfBelongService

	def getRulename(self):
		return self._rulename

	def getEnabled(self):
		return self._enabled

	def getCriteriaToDistinguish(self):
		return self._criteria_to_distinguish

	def getRegex(self):
		return self._regex

	def getIpXoccurDict(self):
		return self._ip_x_occur_dict

	def getAction(self):
		return self._action

	def getAntiaction(self):
		return self._antiaction

	def getThresholdCount(self):
		return self._thresholdCount

	def getJailtime(self):
		return self._jailtime


	def setNameOfBelongService(self, serviceName):
		self._nameOfBelongService = serviceName

	def setRulename(self, rulename):
		self._rulename = rulename

	def setEnabled(self, enabled):
		self._enabled = enabled

	def setCriteriaToDistinguish(self, criteria):
		self._criteria_to_distinguish = criteria

	def setRegex(self, regex):
		self._regex = regex

	def setIpXoccurDict(self, dct):
		self._ip_x_occur_dict = dct

	def updateIpXoccur(self, ipaddr, count):
		self._ip_x_occur_dict.update({ipaddr: count})

	def setAction(self, action):
		self._action = action

	def setAntiaction(self, antiaction):
		self._antiaction = antiaction

	def setThresholdCount(self, thresholdCount):
		self._thresholdCount = thresholdCount

	def setJailtime(self, jailtime):
		self._jailtime = jailtime


class Service(object):
	def __init__(self, name):
		self.name = name
		self.prefs = {}
		self.rules = []
		self._logfile = None
		self._retroactive = False

	def addLogfile(self, logfile):
		self._logfile = logfile

	def getLogfile(self):
		return self._logfile

	def setRetroactive(self, rtrctv):
		if any([eval('rtrctv=="False"'), eval('rtrctv=="false"'), eval('rtrctv==0')]):
		#if rtrctv == "False" or rtrctv == "false" or rtrctv == 0:
			self._retroactive = False
		else:
			self._retroactive = True

	def getRetroactive(self):
		return self._retroactive

	def addPref(self, dictt):
		self.prefs.update(dictt)
		pass

	def getName(self):
		return self.name

	def getPrefs(self):
		return self.prefs

	def getIdsOfRules(self):
		ids = []
		for rule in self.rules:
			ids.append(rule.getId())
		return ids

	def addRule(self, rule):
		# rule with this ID does not exist yet
		if rule.getId() not in self.getIdsOfRules():
			#print str(rule.getId()) + " NOT IN " + str(self.getIdsOfRules())
			self.rules.append(rule)
			print("In context of a service added new rule with ID -> [{}]".format(rule.getId()))
		# ID already present
		else:
			rule = self.getRuleById(rule.getId())
		return rule

	def getRules(self):
		return self.rules

	def getRuleByName(self, name):
		for rule in self.rules:
			if rule.getName() == name:
				return rule

	def getRuleById(self, id):
		for rule in self.rules:
			#print("{} xxxxx {}".format(id, rule.getId())
			if rule.getId() == id:
				return rule
		return None

	def getNoOfRules(self):
		return len(self.rules)


class ServicesManager(object):

	def __init__(self, listOfServices = []):
		self.listOfServices = listOfServices
		pass

	def addService(self, serviceObj):
		self.listOfServices.append(serviceObj)
		return serviceObj

	def getServiceByName(self, name):
		for serv in self.listOfServices:
			if serv.getName() == name:
				return serv

	def getAllServices(self):
		return self.listOfServices

	def getAllServicesNames(self):
		res = []
		for serv in self.listOfServices:
			res.append(serv.getName())
		return res

	def dumpPrefs(self):
		for serv in self.getAllServices():
			print("   [%s]" % (serv.getName()))
			prefs = serv.getPrefs()
			keys = list(prefs.keys())
			for key in keys:
				print("	   {} = {}", key, prefs[key])
			print("") # print an empty line after each service

