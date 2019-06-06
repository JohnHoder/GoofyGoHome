#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
import os
import sys
import datetime
import atexit
import time, sched
from signal import SIGTERM
import re
import fcntl
import stat

import comm_server
from config import Prefs
from rule_executor import RuleExecutor, DbWatcher

DATADIR = 'data/'
CONFDIR = 'conf/'
LOGFILENAME = 'logfile.log'
PIDFILENAME = 'pidfile.pid'
CONFFILENAME = 'conf.conf'

class Daemon(object):
	# Keep instance reference
	_singletonInstance = None

	def __new__(cls, *args, **kwargs):
		if not cls._singletonInstance:
			# Create instance
			cls._singletonInstance = super(Daemon, cls).__new__(Daemon) # object
			pass
		# Return the instance
		return cls._singletonInstance

	def __init__(self, pidfile=None, stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
		self.stdin = stdin
		self.stdout = stdout
		self.stderr = stderr
		self.pidfile = pidfile

		#print(Daemon._singletonInstance)

	@staticmethod
	def getInstance():
		return Daemon._singletonInstance

	def daemonize(self):
		
		# převzato v rámci citační zákonné licence z: https://webdevdesigner.com/q/how-to-make-a-python-script-run-like-a-service-or-daemon-in-linux-60093/
		try:
			pid = os.fork()
			if pid > 0: # if fork succeeded
				#exit first parent
				sys.exit(0)
		except OSError as e:
			sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
			sys.exit(1)

		# decouple from parent environment
		os.chdir("/")
		os.setsid() # start a new session with no controlling terminals
		os.umask(0) # donner tous les droits en lecture/écriture au démon sur les fichiers qu'il crée.
			#0222 with these permissions will be created the socket and also the pidfile
			
		# second fork
		try:
			pid = os.fork()
			if pid > 0: # if fork succeeded
				# exit second parent
				sys.exit(0)
		except OSError as e:
			sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
			sys.exit(1)


		# redirect standard file descriptors
		sys.stdout.flush()
		sys.stderr.flush()
		mode = 'a' if not stat.S_ISCHR(os.stat(self.stdout).st_mode) else 'w'
		si = open(self.stdin, 'r')
		so = open(self.stdout, mode) # or /dev/null for no standard output anywhere
		se = open(self.stderr, mode)
		os.dup2(si.fileno(), sys.stdin.fileno())
		os.dup2(so.fileno(), sys.stdout.fileno())
		os.dup2(se.fileno(), sys.stderr.fileno())

		# write pid file
		atexit.register(self.delpid)

		print("GGH is running in daemon mode [pid -> {}]".format(os.getpid()))

	def writePidToFile(self):
		pid = str(os.getpid())
		print("Writing pid %s to file\n" % pid)
		open(self.pidfile, 'w+').write("%s\n" % pid)

	def lockFile(self, pidfile, timeout=0.5):
		try:
			fd = os.open(pidfile, os.O_CREAT)
		except Exception:
			print("Opening pidfile failed.")

		flags = fcntl.fcntl(fd, fcntl.F_GETFD, 0)
		flags |= fcntl.FD_CLOEXEC
		fcntl.fcntl(fd, fcntl.F_SETFD, flags)

		started = time.time()

		while True:
			try:
				fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
				return True
			except Exception:
				if started > time.time() - timeout:
					print("Couldn't obtain lock but we're within timeout.")
					pass
				else:
					print("Waiting time exceeded.")
					return False
					break # unnecessary but cool
			time.sleep(0.1)

	def doNotRunTwice(self):
		if self.lockFile(self.pidfile) == False:
			pf = open(self.pidfile, 'r')
			pid = int(pf.read().strip())
			if pid:
				sys.stderr.write("GGH is already running under PID [%s]" % pid)
			pf.close()
			sys.exit(1)

	def delpid(self):
		os.remove(self.pidfile)

	def start(self, daemon=True):
		if daemon==True:
			self.daemonize()
		self.doNotRunTwice()
		self.writePidToFile()
		self.run()

	def restart(self, daemon=True, removeLogfile=False):
		self.stop(removeLogfile=removeLogfile)
		self.start(daemon=daemon)


	def stop(self, removeLogfile=False, removeSocketFile=True):
		# Remove logfile
		if removeLogfile == True:
			try:
				os.remove(logfile)
			except:
				pass

		if removeSocketFile == True:
			try:
				sock_path = Prefs().getGeneralPref('SOCKET_PATH')
				os.remove(sock_path)
			except Exception:
				pass

		# get the pid from the pidfile
		try:
			pf = open(self.pidfile, 'r')
			pid = int(pf.read().strip())
			pf.close()
		except IOError:
			pid = None
			#return 1

		if not pid:
			message = "pidfile %s does not exist. GGH not running?\n"
			message += "Start GGH first with `{} --start`".format(sys.argv[0])
			sys.stderr.write(message % self.pidfile)
			return 1# not an error in a restart

		# Try to kill the daemon process
		try:
			while 1:
				os.kill(pid, SIGTERM)
				print("Trying to SIGTERM pid {}".format(pid))
				time.sleep(0.1)
		except OSError as err:
			err = str(err)
			if err.find("No such process") > 0:
				if os.path.exists(self.pidfile):
					os.remove(self.pidfile)
			else:
				print(str(err))
				sys.exit(1)

	def run(self):
		print(datetime.datetime.today())
		print("GoofyGoHome - launching")

		sock_path = Prefs().getGeneralPref('SOCKET_PATH')

		# start DB watcher thread
		dbWatcher = DbWatcher()
		dbWatcher.start()
		#dbWatcher.onThread(dbWatcher.checkEventsNow)

		# start communication server
		commServer = comm_server.CommunicationServer(Daemon.getInstance(), dbWatcher)
		t = threading.Thread(target=commServer.start, args=(sock_path, True), name="comm_server")
		t.start()

		# We don't start this immediately (with value 0)
		# in order to prevent a havoc
		s = sched.scheduler(time.time, time.sleep)
		s.enter(2, 1, watchJournalFiles, (s,))
		s.run()



def watchJournalFiles(sch):
	ruleExecutor = RuleExecutor(prefs=prefs)
	# run self again / recursion
	sch.enter(Prefs().getGeneralPref('DAEMON_SLEEP'), 1, watchJournalFiles, (sch,))


if __name__ == "__main__":

	if sys.version_info[0] < 3:
		raise Exception("Python 3.x or a more recent version is required.")

	if len(sys.argv) >= 2:

		DATADIR_ABS = os.path.dirname(os.path.realpath(__file__)) + '/' + DATADIR
		try:
			os.mkdir(DATADIR_ABS)
		except OSError:
			pass

		logfile = DATADIR_ABS + LOGFILENAME
		pidfile = DATADIR_ABS + PIDFILENAME

		daemon = Daemon(pidfile, stdout=logfile, stderr=logfile) #'/dev/stderr'

		module_path = os.path.dirname(__file__)
		confFile = os.path.join(module_path, CONFDIR + CONFFILENAME)

		if '--start' == sys.argv[1]:

			prefs = Prefs(confFile)

			# create the logfile
			f = open(logfile, 'w')
			f.close()

			if len(sys.argv) >= 3 and sys.argv[2] == '-d':
				daemon.start(daemon=False)
			else:
				daemon.start(daemon=True)

		elif '--stop' == sys.argv[1]:
			daemon.stop(removeLogfile=False)

		elif '--restart' == sys.argv[1]:
			
			# Load prefs
			prefs = Prefs(confFile)

			if len(sys.argv) >= 3 and sys.argv[2] == '-d':
				daemon.restart(daemon=False, removeLogfile=False)
			else:
				daemon.restart(daemon=True, removeLogfile=False)
		else:
			print("Unknown command - use --start, --stop or --restart")
			sys.exit(2)
	else:
		print("Usage: %s --start|--stop|--restart" % sys.argv[0])
		sys.exit(2)
