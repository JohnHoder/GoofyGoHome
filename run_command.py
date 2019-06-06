import fcntl
import logging
import os
import signal
import subprocess
import sys
import time
import locale
#from threading import Lock

# All the code in this file comes from https://github.com/fail2ban/
# All authors are mentioned here: https://github.com/fail2ban/fail2ban/blob/master/THANKS
# In accordance with § 31 odst. 1 písm. b) zákona č. 121/2000 Sb., autorský zákon

_RETCODE_HINTS = {
	127: '"Command not found"'
}

logSys = logging.getLogger(__name__)

PREFER_ENC = locale.getpreferredencoding()

def uni_decode(x, enc=PREFER_ENC, errors='strict'):
	try:
		if isinstance(x, bytes):
			return x.decode(enc, errors)
		return x
	except (UnicodeDecodeError, UnicodeEncodeError): # pragma: no cover - unsure if reachable
		if errors != 'strict': 
			raise
		return x.decode(enc, 'replace')
def uni_string(x):
	if not isinstance(x, bytes):
		return str(x)
	return x.decode(PREFER_ENC, 'replace')



class Utils(object):

	DEFAULT_SLEEP_TIME = 2
	DEFAULT_SLEEP_INTERVAL = 0.2
	DEFAULT_SHORT_INTERVAL = 0.001
	DEFAULT_SHORTEST_INTERVAL = DEFAULT_SHORT_INTERVAL / 100

	@staticmethod
	def execute_action(action):
		if action.startswith('"') and action.endswith('"'):
			action = (str(action)[1:-1])
		Utils.executeCmd(action)
		pass

	@staticmethod
	def buildShellCmd(realCmd, varsDict):
		"""Generates new shell command as array, contains map as variables to
		arguments statement (varsStat), the command (realCmd) used this variables and
		the list of the arguments, mapped from varsDict
		Example:
			buildShellCmd('echo "V2: $v2, V1: $v1"', {"v1": "val 1", "v2": "val 2", "vUnused": "unused var"})
		returns:
			['v1=$0 v2=$1 vUnused=$2 \necho "V2: $v2, V1: $v1"', 'val 1', 'val 2', 'unused var']
		"""
		# build map as array of vars and command line array:
		varsStat = ""
		if not isinstance(realCmd, list):
			realCmd = [realCmd]
		i = len(realCmd)-1
		for k, v in varsDict.iteritems():
			varsStat += "%s=$%s " % (k, i)
			realCmd.append(v)
			i += 1
		realCmd[0] = varsStat + "\n" + realCmd[0]
		return realCmd

	@staticmethod
	def executeCmd(realCmd, timeout=60, shell=True, output=False, tout_kill_tree=True, 
		success_codes=(0,), varsDict=None):
		"""Executes a command.
		Parameters
		----------
		realCmd : str
			The command to execute.
		timeout : int
			The time out in seconds for the command.
		shell : bool
			If shell is True (default), the specified command (may be a string) will be 
			executed through the shell.
		output : bool
			If output is True, the function returns tuple (success, stdoutdata, stderrdata, returncode).
			If False, just indication of success is returned
		varsDict: dict
			variables supplied to the command (or to the shell script)
		Returns
		-------
		bool or (bool, str, str, int)
			True if the command succeeded and with stdout, stderr, returncode if output was set to True
		Raises
		------
		OSError
			If command fails to be executed.
		RuntimeError
			If command execution times out.
		"""
		stdout = stderr = None
		retcode = None
		popen = env = None
		if varsDict:
			if shell:
				# build map as array of vars and command line array:
				realCmd = Utils.buildShellCmd(realCmd, varsDict)

			else: # pragma: no cover - currently unused
				env = _merge_dicts(os.environ, varsDict)
		realCmdId = id(realCmd)
		logCmd = lambda level: logSys.log(level, "%x -- exec: %s", realCmdId, realCmd)
		try:
			#print("realCmd: {}".format(realCmd))
			popen = subprocess.Popen(
				realCmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=shell, env=env,
				preexec_fn=os.setsid  # so that killpg does not kill our process
			)
			# wait with timeout for process has terminated:
			retcode = popen.poll()
			if retcode is None:
				def _popen_wait_end():
					retcode = popen.poll()
					return (True, retcode) if retcode is not None else None
				# popen.poll is fast operation so we can use the shortest sleep interval:
				retcode = Utils.wait_for(_popen_wait_end, timeout, Utils.DEFAULT_SHORTEST_INTERVAL)
				if retcode:
					retcode = retcode[1]
			# if timeout:
			if retcode is None:
				if logCmd: logCmd(logging.ERROR); logCmd = None
				logSys.error("%x -- timed out after %s seconds." %
					(realCmdId, timeout))
				pgid = os.getpgid(popen.pid)
				# if not tree - first try to terminate and then kill, otherwise - kill (-9) only:
				os.killpg(pgid, signal.SIGTERM) # Terminate the process
				time.sleep(Utils.DEFAULT_SLEEP_INTERVAL)
				retcode = popen.poll()
				#logSys.debug("%s -- terminated %s ", realCmd, retcode)
				if retcode is None or tout_kill_tree: # Still going...
					os.killpg(pgid, signal.SIGKILL) # Kill the process
					time.sleep(Utils.DEFAULT_SLEEP_INTERVAL)
					if retcode is None: # pragma: no cover - too sporadic
						retcode = popen.poll()
					#logSys.debug("%s -- killed %s ", realCmd, retcode)
				if retcode is None and not Utils.pid_exists(pgid): # pragma: no cover
					retcode = signal.SIGKILL
		except OSError as e:
			if logCmd: logCmd(logging.ERROR); logCmd = None
			stderr = "%s -- failed with %s" % (realCmd, e)
			logSys.error(stderr)
			if not popen:
				return False if not output else (False, stdout, stderr, retcode)

		std_level = logging.DEBUG if retcode in success_codes else logging.ERROR
		if std_level > logSys.getEffectiveLevel():
			if logCmd: logCmd(std_level-1); logCmd = None
		# if we need output (to return or to log it): 
		if output or std_level >= logSys.getEffectiveLevel():

			# if was timeouted (killed/terminated) - to prevent waiting, set std handles to non-blocking mode.
			if popen.stdout:
				try:
					if retcode is None or retcode < 0:
						Utils.setFBlockMode(popen.stdout, False)
					stdout = popen.stdout.read()
				except IOError as e: # pragma: no cover
					logSys.error(" ... -- failed to read stdout %s", e)
				if stdout is not None and stdout != '' and std_level >= logSys.getEffectiveLevel():
					for l in stdout.splitlines():
						logSys.log(std_level, "%x -- stdout: %r", realCmdId, uni_decode(l))
				popen.stdout.close()
			if popen.stderr:
				try:
					if retcode is None or retcode < 0:
						Utils.setFBlockMode(popen.stderr, False)
					stderr = popen.stderr.read()
				except IOError as e: # pragma: no cover
					logSys.error(" ... -- failed to read stderr %s", e)
				if stderr is not None and stderr != '' and std_level >= logSys.getEffectiveLevel():
					for l in stderr.splitlines():
						logSys.log(std_level, "%x -- stderr: %r", realCmdId, uni_decode(l))
				popen.stderr.close()

		success = False
		if retcode in success_codes:
			logSys.debug("%x -- returned successfully %i", realCmdId, retcode)
			success = True
		elif retcode is None:
			logSys.error("%x -- unable to kill PID %i", realCmdId, popen.pid)
		elif retcode < 0 or retcode > 128:
			# dash would return negative while bash 128 + n
			sigcode = -retcode if retcode < 0 else retcode - 128
			logSys.error("%x -- killed with %s (return code: %s)",
				realCmdId, signame.get(sigcode, "signal %i" % sigcode), retcode)
		else:
			msg = _RETCODE_HINTS.get(retcode, None)
			logSys.error("%x -- returned %i", realCmdId, retcode)
			if msg:
				logSys.info("HINT on %i: %s", retcode, msg % locals())
		if output:
			return success, stdout, stderr, retcode
		return success if len(success_codes) == 1 else (success, retcode)
	
	@staticmethod
	def wait_for(cond, timeout, interval=None):
		"""Wait until condition expression `cond` is True, up to `timeout` sec
		Parameters
		----------
		cond : callable
			The expression to check condition 
			(should return equivalent to bool True if wait successful).
		timeout : float or callable
			The time out for end of wait
			(in seconds or callable that returns True if timeout occurred).
		interval : float (optional)
			Polling start interval for wait cycle in seconds.
		Returns
		-------
		variable
			The return value of the last call of `cond`, 
			logical False (or None, 0, etc) if timeout occurred.
		"""
		#logSys.log(5, "  wait for %r, tout: %r / %r", cond, timeout, interval)
		ini = 1  # to delay initializations until/when necessary
		while True:
			ret = cond()
			if ret:
				return ret
			if ini:
				ini = stm = 0
				if not callable(timeout):
					time0 = time.time() + timeout
					timeout_expr = lambda: time.time() > time0
				else:
					timeout_expr = timeout
				if not interval:
					interval = Utils.DEFAULT_SLEEP_INTERVAL
			if timeout_expr():
				break
			stm = min(stm + interval, Utils.DEFAULT_SLEEP_TIME)
			time.sleep(stm)
		return ret