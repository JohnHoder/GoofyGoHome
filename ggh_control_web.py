#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# GoofyGoHome web control interface
# Inspired by Proxenet by Hugsy, https://github.com/hugsy/proxenet

import os, sys, socket, select, argparse, stat, fcntl
from signal import SIGTERM
import datetime
import json, cgi, time, atexit
import subprocess, tempfile
from urllib.parse import unquote

try:
    from bottle import request, route, get, post, run, static_file, redirect, auth_basic
except ImportError:
    sys.stderr.write("Missing `bottle` package: pip install bottle\n")
    sys.exit(1)

try:
    from pygments import highlight
    from pygments.lexers import get_lexer_for_filename, get_lexer_by_name
    from pygments.formatters import HtmlFormatter
except ImportError:
    sys.stderr.write("Missing `pygments` package: pip install pygments\n")
    sys.exit(1)

from config_validity_checker import ConfigValidator


GGH_DEFAULT_PORT        = 8008
GGH_DEFAULT_HOST        = "0.0.0.0"

# Directive for socket communication protocol
END_SELF                = ">>>"

# stores logins loaded from LOGINSFILENAME
LOGINS                  = {}

# Linux socket file for communication
GGH_SOCKET_PATH         = "/tmp/GGH-control-socket"

# Paths
GGH_ROOT_PATH           = os.path.dirname(os.path.realpath(__file__)) + '/' #.
GGH_HTML_PATH           = GGH_ROOT_PATH + "html/"
GGH_DATA_PATH           = GGH_ROOT_PATH + "data/"
GGH_WEBSERVER_DATA_PATH = GGH_ROOT_PATH + "webserver_data/"
GGH_CONF_PATH           = GGH_ROOT_PATH + "conf/"

# Files
GGH_LOGFILE             = GGH_DATA_PATH + "logfile.log"
GGH_CONFIG_FILE         = GGH_CONF_PATH + "conf.conf"
GGH_LOGINSFILE          = GGH_CONF_PATH + "weblogin.conf"
GGH_WEBSERVER_LOGFILE   = GGH_WEBSERVER_DATA_PATH + "logfile.log"
GGH_WEBSERVER_PIDFILE   = GGH_WEBSERVER_DATA_PATH + "pidfile.pid"


def is_GGH_running():
    return os.path.exists(GGH_SOCKET_PATH)

def success(m):
    return """<div class="alert alert-success alert-dismissible" role="alert">{}</div>""".format(m)

def error(m):
    return """<div class="alert alert-danger alert-dismissible" role="alert">{}</div>""".format(m)

def alert(m):
    return """<div class="alert alert-warning alert-dismissible" role="alert">{}</div>""".format(m)

def redirect_after(n, location):
    return """<script>setTimeout('window.location="{:s}"', {:d})</script>""".format(location, n*1000)

def not_running_html():
    return error("<b>GGH daemon</b> is not running")

def no_logfile_html():
    return error("Logs are not saved to file.")


def recv_until(sock, pattern=END_SELF):
    data = ""
    while True:
        data += sock.recv(1024).decode()
        if data.endswith(pattern):
            break
    return data

def format_result(res, breakline="<br>"):
    d = res.replace('\n', breakline)
    d = d[:-3]
    print(d)
    return d

def sr(msg, breakline="<br>", no_recv=False):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(GGH_SOCKET_PATH)
    except:
        return not_running_html()

    s.send((msg.strip() + '\n').encode('utf-8'))
    if no_recv == False:
        res = recv_until(s)
        res = format_result(res, breakline)
    else:
        res = None
    s.close()
    return res

@get('/proc')
def proc_cmd():
    cmd = request.query.cmd
    print(unquote(cmd))
    res = sr(cmd, breakline='\n')
    try:
        res = json.loads(res)
        print("1\n")
    except ValueError:
        res = res
    return res


@route('/img/logo')
def logo():
    return static_file("/gghlogo.png", root=GGH_HTML_PATH+"/img")

@route('/img/spoiler-plus.gif')
def spoiler_plus():
    return static_file("/spoiler-plus.gif", root=GGH_HTML_PATH+"/img")

@route('/js/bootstrap')
def js_bootstrap():
    return static_file("/bootstrap.min.js", root=GGH_HTML_PATH+"/js")

@route('/css/bootstrap')
def css_boostrap():
    return static_file("/bootstrap.min.css", root=GGH_HTML_PATH+"/css")

@route('/css/bootstrap-theme')
def css_boostrap_theme():
    return static_file("/bootstrap-theme.min.css", root=GGH_HTML_PATH + "/css")

@route('/css/custom')
def css_custom():
    return static_file("/custom.css", root=GGH_HTML_PATH + "/css")

@route('/termlib.js')
def js_termlib():
    return static_file("/termlib/termlib.js", root=GGH_HTML_PATH)

@route('/shell.js')
def js_termlib_inst():
    return static_file("/termlib/shell.js", root=GGH_HTML_PATH)

def check(username, password):
    for user, pw in LOGINS.items():
        if username == user and password == pw:
            return True
    return False

@route('/')
@auth_basic(check)
def index():
    return events()

def build_html(**kwargs):
    header = """<!DOCTYPE html><html lang="en"><head>"""
    header+= """<script src="/js/bootstrap"></script>"""
    header+= """<link rel="stylesheet" href="/css/bootstrap">"""
    header+= """<link rel="stylesheet" href="/css/bootstrap-theme">"""
    header+= """<link rel="stylesheet" href="/css/custom">"""
    header+= """<style>{}</style>""".format(HtmlFormatter().get_style_defs('.highlight'))
    header+= "\n".join( kwargs.get("headers", []) )
    header+= """<title>{}</title></head>""".format( kwargs.get("title", "") )

    body = """<body><div class="container">
    <div><img src="/img/logo" onclick="window.open('/', '_self')" style="cursor:pointer;"></div>
    <div class="row"><div class=col-md-12>
    <ul class="nav nav-tabs nav-justified">"""

    tabs = []
    #if is_GGH_running():
    tabs += ["events", "eventlog", "shell", "config", "log", "about"]

    for tab in tabs:
        body += """<li {2}><a href="/{0}">{1}</a></li>""".format(tab, tab.capitalize(), "class='active'" if tab==kwargs.get("page") else "")

    body += """<li><a href="/rstquit">Restart & Quit</a></li>"""
    # else:
    #     body += """<li><a href="/start">Start</a></li>"""

    body += """</ul></div></div>
    <div class="row"><div class="col-md-12"><br></div></div>
    <div class="row">
    </div><div class="col-md-12">{}</div>
    </div></body>""".format(kwargs.get("body", ""))
    footer = """</html>"""
    return header + body + footer

@get('/shell')
def shell():
    html = ""
    html += """<div class="panel panel-default">"""
    html += """<div class="panel-heading"><h3 class="panel-title">Shell</h3></div>"""
    html += """<div class="panel-body"><ul>"""
    html += """<script language="JavaScript" type="text/javascript" src="/termlib.js"></script>"""
    html += """<script language="JavaScript" type="text/javascript" src="/shell.js"></script>"""

    html += """<body onload="termOpen();">"""
    html += """<img href="javascript:termOpen()"></a>"""
    html += """<div id="termDiv" style="position:relative; visibility: hidden; z-index:1;"></div>"""
    html += """</body>"""

    html += """</ul></div></div>"""

    return build_html(body=html, page="shell", title="Shell - GoofyGoHome")


@post('/start')
def do_start():
    cmd = []

    cmd.append(GGH_ROOT_PATH + "ggh_daemon.py")
    cmd.append("start")
   
    popup = "Launching <b>GGH</b> with command:{}<br/><br/>".format(cmd)
    popup+= """<div style="font: 100% Courier,sans-serif;">""" + " ".join(cmd) + """</div>"""
    msg = alert(popup)
    subprocess.call(cmd)
    msg+= redirect_after(2, "/")
    return build_html(body=msg)

@get('/quit')
def quit():
    if not is_GGH_running():
        return build_html(body=not_running_html())
    sr("daemon stop", no_recv=True)
    msg = ""
    msg+= alert("Shutting down <b>GGH daemon</b>.")
    # Return to main page
    msg+= redirect_after(2, "/")
    return build_html(body=msg)

@get('/restart')
def restart():
    
    if not is_GGH_running():
        return build_html(body=not_running_html())
    sr("daemon stop", no_recv=True)
    msg = ""
    msg+= alert("Restarting <b>GGH daemon</b>.")
    # Return to main page
    msg+= redirect_after(5, "/")
    do_start()
    return build_html(body=msg)

@get('/rstquit')
def restart_quit():

    html = ""
    html += """<div class="panel panel-default">"""
    html += """<div class="panel-heading"><h3 class="panel-title">Restart & Quit</h3></div>"""
    html += """<div class="panel-body"><ul>"""

    if not is_GGH_running():
        return build_html(body=not_running_html())
    else:
        html += """<li><a href="#" onclick="var c=confirm('Are you sure to restart?');if(c){window.location='/restart';}">Restart</a></li>"""
        html += """<li><a href="#" onclick="var c=confirm('Are you sure to quit?');if(c){window.location='/quit';}">Quit</a></li>"""

    html += "</ul></div></div>"
    # msg = ""
    # msg+= alert("Restarting <b>GGH</b>")
    # msg+= redirect_after(2, "/events")
    return build_html(body=html)


@get('/events')
def events():
    if not is_GGH_running():
        return build_html(body=not_running_html())

    res = sr("db events show json")
    try:
        events = json.loads(res)['events']
    except Exception:
        html = "~ An error occured"
        return build_html(body=html, title="Events - GoofyGoHome", page="events")
    print(events)

    html = ""
    html += """<div class="panel panel-default">"""
    html += """<div class="panel-heading"><h3 class="panel-title">Detected Events</h3></div>"""
    html += """<table class="table table-hover table-condensed">"""
    html += "<tr><th>ID</th><th>Service</th><th>Rule</th><th>Distingueur</th><th>Time of Event</th><th>Expires (s)</th><th>Antiaction</th></tr>"

    # for event in events:
    #     html += "<tr>"
    #     for key in event.keys():
    #         html += "<th>{}</th>".format(key)
    #         #print
    #     html += "</tr>"
    #     break

    for event in events:
        html += """
                <script>
                function dnslookup(eventid, ip){
                    var x = document.getElementById("div_content_".concat(eventid));
                    if (x.style.display === "none") {
                        x.style.display = "block";
                    } else {
                        x.style.display = "none";
                    }

                    var xhr = new XMLHttpRequest();
                    xhr.open('GET', '/proc?cmd=dnslookup%20'.concat(ip));
                    xhr.send();
                    xhr.onreadystatechange = function() {
                        if(xhr.readyState === 4) {
                            if(xhr.status === 200) {
                                //alert(xhr.responseText);
                                var y = document.getElementById("div_content_".concat(eventid)).innerHTML=(xhr.responseText);
                            } else{
                                //alert('Error: '+xhr.status); // An error occurred during the request
                                document.getElementById("div_content_".concat(eventid)).innerHTML="Failed"
                            }
                        }
                    }
                }
                </script>
                """

        html += """<tr><td>{}</td><td>{}</td><td>{}</td>""".format(event['id'], event['belongService'], event['comesFromRule'])

        try:
            socket.inet_aton(event['distingueur'])
            html += """
                <td>
                    <img src="/img/spoiler-plus.gif" style="cursor: pointer;" hspace="4px" onclick="dnslookup({},'{}')">{}
                    <div id="div_content_{}" style='display:none;'></div>
                </td>
            """.format(event['id'], event['distingueur'], event['distingueur'], event['id'])
        except socket.error:
            html += """<td>{}</td>""".format(event['distingueur'])

        html += """<td>{}</td><td>{}</td><td>{}</td>""".format(event['timeOfEvent'], event['eventExp'], event['antiaction'])

        html += """<td><button type="button" class="btn btn-default btn-xs" data-toggle="button" aria-pressed="false" onclick="window.location='/event/{}/release'">Release</button></td>""".format(event["id"])
        html += "</tr>"
    html += "</table></div>"""

    return build_html(body=html, title="Events - GoofyGoHome", page="events")

@get('/event/<id:int>/release')
def event_remove(id):
    if not is_GGH_running():
        return build_html(body=not_running_html())
    res = sr("db events release {}".format(id))
    html = ""
    html += error("""{}""".format(res))
    html+= redirect_after(2, "/events")
    return build_html(body=html, page="events")


@get('/eventlog')
def eventlog():
    if not is_GGH_running():
        return build_html(body=not_running_html())

    res = sr("db eventlog show json")
    try:
        events = json.loads(res)['eventlog']
    except Exception:
        html = "~ An error occured"
        return build_html(body=html, title="Eventlog - GoofyGoHome", page="eventlog")
    print(events)

    html = ""
    html += """<div class="panel panel-default">"""
    html += """<div class="panel-heading"><h3 class="panel-title">Detected Events</h3></div>"""
    html += """<table class="table table-hover table-condensed">"""
    html += "<tr><th>ID</th><th>Service</th><th>Rule</th><th>Distingueur</th><th>Time of Event</th></tr>"

    # for event in events:
    #     html += "<tr>"
    #     for key in event.keys():
    #         html += "<th>{}</th>".format(key)
    #         #print
    #     html += "</tr>"
    #     break

    for event in events:
        html += "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td>".format(event['id'], event['belongService'], event['comesFromRule'], event['distingueur'], event['timeOfEvent'])

        html += """<td><button type="button" class="btn btn-default btn-xs" data-toggle="button" aria-pressed="false" onclick="window.location='/eventlog/{}/remove'">Remove</button></td>""".format(event["id"])
        html += "</tr>"
    html += "</table></div>"""

    return build_html(body=html, title="Eventlog - GoofyGoHome", page="eventlog")

@get('/eventlog/<id:int>/remove')
def event_remove(id):
    if not is_GGH_running():
        return build_html(body=not_running_html())
    res = sr("db eventlog remove {}".format(id))
    html = ""
    html += error("""{}""".format(res))
    html+= redirect_after(2, "/eventlog")
    return build_html(body=html, page="eventlog")


@get('/about')
def about():
    if not is_GGH_running():
        return build_html(body=not_running_html())

    res = sr("version")
    #version = json.loads(res)
    html = ""
    html += """<div class="panel panel-default">"""
    html += """<div class="panel-heading"><h3 class="panel-title">Version information</h3></div>"""
    html += """<div class="panel-body"><ul>"""
    html += "<h3 class=\"panel-title\">Version</h3>"
    html += ''.join(["<li>{}</li>".format(res)])
    html += """</ul></div></div>"""

    return build_html(body=html, title="About - GoofyGoHome", page="about")

@get('/config')
def config():
    # if not is_GGH_running():
    #     return build_html(body=not_running_html())
    fpath = os.path.realpath(GGH_CONFIG_FILE)
    if not os.path.isfile(fpath):
        return build_html(body=error("""Config file <b>{}</b> does not exist.""".format(fpath)))

    with open(fpath, 'r') as f:
        code = f.read()

    lexer = get_lexer_by_name("bash")
    html  = """"""
    html += """<div class="panel panel-default">"""
    html += """<div class="panel-heading"><h3 class="panel-title">{}</h3></div>""".format(fpath)
    html += """<div class="panel-body">"""
    html += """<button onclick="window.location.href='/configedit'">Edit</button><br/><br/>"""
    html += """{}""".format(highlight(code, lexer, HtmlFormatter()))
    html += """</div>"""
    html += """</div>"""
    return build_html(body=html, page="config", title="Viewing config file '{}'".format(fpath))

@get('/configedit')
def config_edit():
    num_of_lines = 0
    if not os.access(GGH_CONFIG_FILE, os.R_OK):
        open(GGH_CONFIG_FILE, 'a+')
    f = open(GGH_CONFIG_FILE, 'r+')
    code = f.read()
    # Get number of lines
    f.seek(0, 0)
    num_of_lines = sum(1 for line in f) + 5
    f.close()
    
    html  = ""
    if request.params.get("new"):
        html += success("New configuration written. Daemon restart needed for changes to take effect.")
    elif request.params.get("conferror"):
        if request.params.get("ret"):
            html += error(str(request.params.get("ret")))

    html += """<div class="panel panel-default">"""
    html += """<div class="panel-heading"><h3 class="panel-title">Edit plugin config</h3></div>"""
    html += """<div class="panel-body"><form method="POST">"""
    html += """<textarea name="config" cols="143" rows="{}" style="font: 100% Courier,sans-serif;">{}</textarea><br/>""".format(num_of_lines, code)
    html += """<button type="submit" class="btn btn-primary">Save</button><br/>"""
    html += """</form></div>"""
    html += """</div>"""
    return build_html(body=html, page="rc", title="Viewing plugin configuration file")


@post('/configedit')
def config_write():
    newconf = request.params.get("config")
    #print(newconf)
    # Check validity of the new config
    cfg = {}
    try:
        # To be checked
        cfg = ConfigValidator(newconf)
    except Exception as e:
        print(e)
        redirect("/configedit?conferror=1&ret={}".format(e))
    else:
        with open(GGH_CONFIG_FILE, 'w') as f:
            f.write(newconf)
        redirect("/configedit?new=1")
    return

@get('/log')
def view_logfile():
    global GGH_LOGFILE

    if not is_GGH_running(): return build_html(body=not_running_html())
    if GGH_LOGFILE in (None, "", "/dev/null"):
        return build_html(body=no_logfile_html())

    with open(GGH_LOGFILE, 'r') as f:
        logs = f.read()

    # Refresh every 5 seconds
    #headers = ["""<meta http-equiv="refresh" content="5"/>""", ]
    headers = []

    html  = ""
    html += """<div class="panel panel-default">"""
    html += """<div class="panel-heading"><h3 class="panel-title">Logs from '{}'</h3></div>""".format(GGH_LOGFILE)
    html += """<div class="panel-body">"""
    html += """<textarea name="logs" cols="143"  rows="30" style="font: 100% Courier,sans-serif;" readonly>{}</textarea><br/>""".format(logs)
    html += """</div>"""
    html += """</div>"""
    return build_html(body=html, page="log", title="Log file", headers=headers)

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
                    # with these permissions will be created the socket and also the pidfile
                    # 0222 possibly
            
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
        x1 = open(self.stdout, 'w+')
        x1.close()
        mode = 'a' if not stat.S_ISCHR(os.stat(self.stdout).st_mode) else 'w+'
        si = open(self.stdin, 'r')
        so = open(self.stdout, mode) # or /dev/null for no standard output anywhere
        se = open(self.stderr, mode)
        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())

        # write pid file
        atexit.register(self.delpid)
        
        #open(self.pidfile, 'w+').write("%s\n" % pid) # THIS IS HERE WRONG?

        print("{} is running in daemon mode [pid -> {}]".format(sys.argv[0], os.getpid()))

    def openAndLockFile(self, pfile, pid):
        pf = open(pfile, 'a+')
        try:
            fcntl.lockf(pf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            pid = int(pf.read().strip())
            pf.close()
            if pid:
                msg = "We are already running. (Based on failed locking of " + pfile + ")" + "\n" + "PID of the already running instance of GGH --- " + str(pid)
                sys.stderr.write(msg)
                sys.exit(1)
        # Write PID to file
        open(self.pidfile, 'w+').write("%s\n" % pid)
        return True

    def doNotRunTwice(self):
        pid = str(os.getpid())
        self.openAndLockFile(self.pidfile, pid)

    def delpid(self):
        os.remove(self.pidfile)

    def startAsDaemon(self):
        # Check for a pidfile to see if the daemon already runs
        #self.openAndLockFile(self.pidfile)
        self.daemonize()
        self.doNotRunTwice()
        self.run()

    def startOnTTY(self):
        # Check for a pidfile to see if the daemon already runs
        #self.openAndLockFile(self.pidfile)
        #self.daemonize()
        self.doNotRunTwice()
        self.run()

    def stop(self):
        # Remove logfile
        try:
            os.remove(logfile)
        except:
            pass

        # get the pid from the pidfile
        try:
            pf = open(self.pidfile, 'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None

        if not pid:
            message = "pidfile %s does not exist. Daemon not running?\n"
            sys.stderr.write(message % self.pidfile)
            return # not an error in a restart

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

    def restart(self):
        self.stop()
        self.start()

    def run(self):
        print(datetime.datetime.today())


if __name__ == "__main__":

    __desc__ = """ggh_control_web.py is a Web interface to control GGH daemon"""
    parser = argparse.ArgumentParser(description = __desc__)

    parser.add_argument("-d", "--debug", default=False, action="store_true",
                        dest="debug", help="Enable debug mode")

    parser.add_argument("-H", "--host", default=GGH_DEFAULT_HOST, type=str, dest="host",
                        help="IP address to bind")

    parser.add_argument("-P", "--port", default=GGH_DEFAULT_PORT, type=int, dest="port",
                        help="port to bind")

    parser.add_argument("-s", "--stop", default=False, action="store_true",
                        dest="stop", help="Stops web control server")

    args = parser.parse_args()

    try:
        os.mkdir(GGH_WEBSERVER_DATA_PATH)
    except OSError:
        pass

    daemon = Daemon(GGH_WEBSERVER_PIDFILE, stdout=GGH_WEBSERVER_LOGFILE, stderr=GGH_WEBSERVER_LOGFILE)

    if args.stop:
        daemon.stop()
        sys.exit(0)

    if not args.debug:
        print("Starting web server as daemon on http://%s:%d" % (args.host, args.port))
        daemon.startAsDaemon()
    else:
        daemon.startOnTTY()


    # Load web login credentials from LOGINSFILENAME
    f = open(GGH_LOGINSFILE)
    data = f.readlines()
    f.close()
    data = [x.strip() for x in data]
    for i in data:
        x = i.split(':')
        LOGINS[x[0]] = x[1]
    #print(LOGINS)

    # Run bottle server
    run(host=args.host, port=args.port, debug=args.debug)

    sys.exit(0)
