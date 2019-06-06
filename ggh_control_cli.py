#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import socket
import datetime
import json
import readline
import pprint
import logging

END_SELF = ">>>"

FORMAT = '%(asctime)-15s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO,format=FORMAT)

GGH_SOCKET_PATH = "/tmp/GGH-control-socket"

command_list = []

def connect(sock_path):
    if not os.path.exists(sock_path):
        logging.critical("Socket does not exist.")
        logging.error("Is GGH started?")
        return None

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(sock_path)
    except socket.error as se:
        logging.error("Failed to connect: %s" % se)
        return None

    logging.info("Connected")
    return sock


def recv_until(sock, pattern=END_SELF):
    data = ""
    while True:
        data += sock.recv(1024).decode()
        if data.endswith(pattern):
            break
    return data


def list_commands(sock):
    #banner = recv_until(sock)
    sock.send("help\n\n".encode('utf-8'))
    res = recv_until(sock)
    #print(res)
    data, prompt = res[:-len(END_SELF)], res[-len(END_SELF):]
    js = json.loads(data)
    #print(js)
    # print available commands
    print("Available commands:")
    for key, value in js["Command list"].items():
        print("  ", key, " -> ", value)
    print("")
    sock.send("\n".encode('utf-8'))
    # IMPORTANT !!!
    res = recv_until(sock)

    return js["Command list"].keys()


def input_loop(cli):
    if not cli:
        return

    do_loop = True

    try:
        while True:
            if not do_loop:
                #recv_until(cli)
                sys.exit(0)
                break

            res = recv_until(cli)
            # Strip END_SELF overhead
            data = res[:-len(END_SELF)]
            prompt = "ggh-cli$ "
            #print("cmd$ {}".format(prompt))
            #print("GGH cli -> ")
            try:
                js = json.loads(data)
                print(json.dumps(js, sort_keys=False, indent=4, separators=(',', ': ')))
            except:
                # if it was not just ENTER
                if data != "":
                    print(data)
            cmd = input(prompt)
            if cmd.strip() == "quit":
                do_loop = False
            elif cmd.strip() == "help":
                list_commands(cli)
            else:
                # Send
                cli.send((cmd.strip()+"\n").encode('utf-8'))
                

    except KeyboardInterrupt:
        logging.info("Exiting client")
    except EOFError:
        logging.info("End of stream")
    except Exception as e:
        logging.error("Unexpected exception: %s" % e)
    finally:
        cli.close()

    return


if __name__ == "__main__":
    sock = connect(GGH_SOCKET_PATH)
    if sock is None:
        sys.exit(1)

    command_list = list_commands(sock)
    #print(command_list)
    input_loop(sock)
    sys.exit(0)
