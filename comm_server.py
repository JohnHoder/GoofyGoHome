#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asynchat
import asyncore
import errno
import fcntl
import os
import socket
import sys
import threading
import traceback

#from cmd_processor import CommandProcessor
import cmd_processor
import ggh_daemon

SIGNS = {
  "END_SELF": b">>>",
  "END_CLIENT": b"\n",
  "CLOSE": b"<<<CLOSE>>>",
  "EMPTY": b""
}

class RequestHandler(asynchat.async_chat):
	
	def __init__(self, conn, cmdProc):
		asynchat.async_chat.__init__(self, conn)
		self.__conn = conn
		self.__cmdProc = cmdProc
		self.buf = []
		self.set_terminator(SIGNS['END_CLIENT'])

	def collect_incoming_data(self, data):
		self.buf.append(data)

	def found_terminator(self):
		message = SIGNS['EMPTY'].join(self.buf)

		if message == SIGNS['CLOSE']:
			self.close_when_done()
			return
		# Give the message to cmdProc
		elif self.__cmdProc:
			message = self.__cmdProc.proceed(message)
			# pop buffer
			self.buf = []
		else:
			message = ['COMM_PROC NOT IMPLEMENTED.']
			# pop buffer
			self.buf = []
		#print(message)
		# Send to the client
		self.push(message.encode('utf-8'))

	def __close(self):
		if self.__conn:
			conn = self.__conn
			self.__conn = None
			try:
				conn.shutdown(socket.SHUT_RDWR)
				conn.close()
			except socket.error:
				pass

	def handle_close(self):
		self.__close()
		asynchat.async_chat.handle_close(self)

# Taken from Fail2Ban - https://github.com/fail2ban/fail2ban/blob/0.11/fail2ban/server/asyncserver.py
# In accordance with § 31 odst. 1 písm. a) zákona č. 121/2000 Sb., autorský zákon

def loop(active, timeout=None, use_poll=False, err_count=None):
	"""Custom event loop implementation -- credits to Fail2Ban (github.com/fail2ban)
	Uses poll instead of loop to respect `active` flag,
	to avoid loop timeout mistake: different in poll and poll2 (sec vs ms),
	and to prevent sporadic errors like EBADF 'Bad file descriptor' etc. (see gh-161)
	"""
	if not err_count:
		err_count={}
	err_count['listen'] = 0
	if timeout is None:
		timeout = 2
	poll = asyncore.poll
	if callable(use_poll):
		poll = use_poll
	elif use_poll and asyncore.poll2 and hasattr(asyncore.select, 'poll'):
		# Server listener (select) uses poll
		# poll2 expected a timeout in milliseconds (but poll and loop in seconds):
		timeout = float(timeout) / 1000
		poll = asyncore.poll2
	# Poll as long as active:
	while active():
		try:
			poll(timeout)
			if err_count['listen']:
				err_count['listen'] -= 1
		except Exception as e:
			if not active():
				break
			err_count['listen'] += 1
			if err_count['listen'] < 20:
				# errno.ENOTCONN - 'Socket is not connected'
				# errno.EBADF - 'Bad file descriptor'
				if e.args[0] in (errno.ENOTCONN, errno.EBADF):
					print('Server connection was closed: {0}'.format(str(e)))
			elif err_count['listen'] == 20:
				print('Too many errors - stop logging connection errors')
			elif err_count['listen'] > 100:
				if (
						# [Errno 24] Too many open files
						e.args[0] == errno.EMFILE
						or sum(err_count.itervalues()) > 1000
				):
					print("Too many errors - critical count reached {0}".format(err_count))
					break

# extends asyncore and dispatches connection requests to RequestHandler.
class AsyncServer(asyncore.dispatcher):

	def __init__(self, cmdProc):
		asyncore.dispatcher.__init__(self)
		#print(daemonInstance)
		self.__cmdProc = cmdProc
		self.__sock = "/tmp/GGH-control-socket"
		self.__init = False
		self.__active = False
		self.__errCount = {'accept': 0, 'listen': 0}
		self.onstart = None

	def handle_accept(self):
		try:
			conn, addr = self.accept()
			#print("Client connected")
		except Exception as e: # pragma: no cover
			self.__errCount['accept'] += 1
			if self.__errCount['accept'] < 10:
				print("Accept socket error: {0}".format(e))
			elif self.__errCount['accept'] > 100:
				if (
					  (isinstance(e, socket.error) and e.args[0] == errno.EMFILE) # [Errno 24] Too many open files
					or sum(self.__errCount.itervalues()) > 1000
				):
					print("Too many errors - critical count reached {0}".format(self.__errCount))
					self.close()
			return
		# Reset errCount by one if accept succeeds
		if self.__errCount['accept']:
			self.__errCount['accept'] -= 1;
		AsyncServer.__markCloseOnExec(conn)
		# instance to handle the request/response on the incoming connection
		RequestHandler(conn, self.__cmdProc)
	
	# Starts the communication server.
	# @param sock: socket file.
	# @param force: remove the socket file if exists.
	def start(self, sock, force, timeoutx=None, use_poll=False):
		self.__worker = threading.current_thread()
		self.__sock = sock
		# Remove socket
		if os.path.exists(sock):
			print("Socket already exists")
			if force:
				print("Enforcing on - removing socket file")
				self._remove_sock()
			else:
				print("Server already running")
		# Creates the socket.
		self.create_socket(socket.AF_UNIX, socket.SOCK_STREAM)
		self.set_reuse_addr()
		try:
			self.bind(sock)
		except Exception: # pragma: no cover
			print("Unable to bind socket {0}".format(self.__sock))
		AsyncServer.__markCloseOnExec(self.socket)
		self.listen(1)
		# Sets the init flag.
		self.__init = self.__loop = self.__active = True
		# Execute on start event (server ready):
		if self.onstart:
			self.onstart()
		# Event loop as long as active:
		asyncore.loop(timeout=timeoutx, use_poll=use_poll)
		#self.thread = threading.Thread(target=loop,kwargs = {'timeout':timeoutx, 'use_poll':use_poll})
		#self.thread.start()
		self.__active = False
		# Cleanup all
		self.close()

	# Stops/closes the communication server.
	def close(self):
		stopflg = False
		if self.__active:
			self.__loop = False
			# shutdown socket here:
			if self.socket:
				try:
					self.socket.shutdown(socket.SHUT_RDWR)
				except socket.error:
					pass
			# close connection:
			asyncore.dispatcher.close(self)
			# If not the loop thread (stops self in handler), wait (a little bit) 
			# for the server leaves loop, before remove socket
			if threading.current_thread() != self.__worker:
				wait_for(lambda: not self.__active, 1)
			stopflg = True
		# Remove socket (file) only if it was created:
		if self.__init and os.path.exists(self.__sock):
			self._remove_sock()
			print("Removed socket file {0}".format(self.__sock))
		if stopflg:
			print("Socket shutdown")
		self.__active = False

	# better remains a method (not a property) since used as a callable for wait_for
	def isActive(self):
		return self.__active

	# Safe remove in multithreaded mode
	def _remove_sock(self):
		try:
			os.remove(self.__sock)
		except OSError as e:
			if e.errno != errno.ENOENT:
				raise

	# Marks socket as close-on-exec to avoid leaking file descriptors when
	# running actions involving command execution.
	# @param sock: socket file.
	@staticmethod
	def __markCloseOnExec(sock):
		fd = sock.fileno()
		flags = fcntl.fcntl(fd, fcntl.F_GETFD)
		fcntl.fcntl(fd, fcntl.F_SETFD, flags|fcntl.FD_CLOEXEC)


class CommunicationServer(object):
	def __init__(self, daemonInstance, dbWatcher):
		self.daemonInstance = daemonInstance
		self.cmdProc = cmd_processor.CommandProcessor(self.daemonInstance, dbWatcher)

	def start(self, sock, force=True):
		try:
			print(ggh_daemon.Daemon.getInstance())
			self.__asyncServer = AsyncServer(self.cmdProc)
			self.__asyncServer.start(sock, force)
		except Exception as e:
			print(str(e))
