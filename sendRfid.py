#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""" HMS Meeting Sign-In UPD RFID Sender

  Author: Matt Lloyd
  Copyright (c) 2019 Nottingham Hackspace

  The MIT License (MIT)

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in all
  copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
  SOFTWARE.
"""
import sys
from time import time, sleep
import os
import socket
import json

TO_PORT = 7861

sock = socket.socket(socket.AF_INET, # Internet
                     socket.SOCK_DGRAM) # UDP

sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
if sys.platform == 'darwin':
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)


if len(sys.argv) == 1:
    print("You need to speficy a UID to send")
    sys.exit()

uid = sys.argv[1].encode()

try:
    sock.sendto(uid, ("<broadcast>", TO_PORT))
except socket.error as msg:
    if msg[0] == 49 or msg[0] == 101:
        try:
            sock.sendto(uid, ('127.0.0.255', TO_PORT))
        except socket.error as msg:
            print("Failed to send 127, Error code : {} Message: {}".format(msg[0], msg[1]))
        else:
            print("Sent 127: {}".format(uid))
    else:
        print("Failed to send broadcast, Error code : {} Message: {}".format(msg[0], msg[1]))
else:
    print("Sent broadcast: {}".format(uid))

sock.close()