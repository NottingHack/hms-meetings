#!/usr/bin/env kivy2
# -*- coding: utf-8 -*-
""" HMS Meeting Sign-In

  Requirements
  pi-rc522 (https://github.com/kevinvalk/pi-rc522.git)

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
from kivy.app                   import App
from kivy.clock                 import Clock
from kivy.network.urlrequest    import UrlRequest
from kivy.uix.label             import Label
from kivy.uix.screenmanager     import ScreenManager, Screen
from kivy.core.window           import Window
from kivy.properties            import ObjectProperty, StringProperty, BooleanProperty

from binascii import hexlify
import urllib
import time
import Queue
import threading
import socket
import select

class RFID():
    _reader = False
    _listenPort = 7861
    _UDPListenTimeout = 2   # timeout for UDP listen

    def __init__(self):
        self.tRFIDStop = threading.Event()
        self.qRFID = Queue.Queue()
        try:
            global pirc522
            import pirc522 as pirc522
            self._reader = pirc522.RFID(pin_irq = None, antenna_gain = 7)
        except ImportError:
            print("RFID: Error importing pirc522. Will listen for UDP on {}".format(self._listenPort))
        except:
            print("RFID: Error importing pirc522 Will listen for UDP on {}".format(self._listenPort))

    def startRFIDRead(self):
        if self._reader:
            self.tThread = threading.Thread(name='tRC522read', target=self._rc522Thread)
        else:
            self.tThread = threading.Thread(name='tUDPListen', target=self._udpThread)

        try:
            self.tThread.start()
        except:
            print("RFID: Failed to start thread: {}".format(self.tThread.name))

    def stopRFIDRead(self):
        print("RFID: Stopping thread")
        self.tRFIDStop.set()

    def _rc522Thread(self):
        """ pi-rc522 Read thread
            We read for new RFID uid's and post to qRFID
        """
        print("tRC522read: Thread started")
        lastUid = None

        while (not self.tRFIDStop.is_set()):
            uid = self._reader.read_id()
            if uid is not None:
                uidNumber = hexlify(bytearray(uid))
                if lastUid != uidNumber:
                    lastUid = uidNumber
                    try:
                        self.qRFID.put_nowait(uidNumber)
                    except Queue.Full:
                        print("tRC522read: Failed to put {} on qRFID as it's full".format(uidNumber))

            self.tRFIDStop.wait(0.1)
        print("tRC522read: Thread stopped")

    def _udpThread(self):
        """ UDP Read thread
            We listen via UDP for a new UID and post to qRFID
        """
        print("tUDPListen: Thread started")
        lastUid = None

        try:
            UDPListenSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except socket.error:
            print("tUDPListen: Failed to create socket, Exiting")
            return

        UDPListenSocket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        UDPListenSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            UDPListenSocket.bind(("", self._listenPort))
        except socket.error:
            print("tUDPListen: Failed to bind port, Exiting")
            return

        UDPListenSocket.setblocking(0)

        print("tUDPListen: listening")
        while (not self.tRFIDStop.is_set()):
            datawaiting = select.select([UDPListenSocket], [], [], self._UDPListenTimeout)
            if datawaiting[0]:
                (uidNumber, address) = UDPListenSocket.recvfrom(8192)
                print("tUDPListen: Received: {} From: {}".format(uidNumber, address))
                if lastUid != uidNumber:
                    lastUid = uidNumber
                    try:
                        self.qRFID.put_nowait(uidNumber)
                    except Queue.Full:
                        print("{}: Failed to put {} on qRFID as it's full".format(self.tThread.name, uidNumber))

        print("tUDPListen: Thread stopping")
        try:
            UDPListenSocket.close()
        except socket.error:
            print("tUDPListen: Failed to close socket")
        print("tUDPListen: Thread stopped")
        return

class HMS():
    # default client credentials
    clientId = '9'
    clientSecret = 'ctYIiYVX1oIVrOSXroPn2jRIkxCb4FsMEVpjoVYb'

    production = False
    _baseURLDev = 'https://hmsdev'
    _baseURLProd = 'https://lspace.nottinghack.org.uk'
    _tokenURL = '{baseURL}/oauth/token'
    _meetingNextURL = '{baseURL}/api/client/governance/meeting/next'
    _meetingURL = '{baseURL}/api/client/governance/meeting/{meeting}'
    _meetingCheckInRfidURL = '{baseURL}/api/client/governance/meeting/{meeting}/checkInRfid'

    _token = []
    _meetinId = None

    _defaultStatusMessage = 'Scan RFID to Check-in'

    checkInScreen = None
    connecScreen = None

    rfid = RFID()

    def getToken(self, success, fail):
        self._tokenSuccessCallback = success
        self._tokenFailCallback = fail
        params = urllib.urlencode({
            'grant_type': 'client_credentials',
            'client_id': self.connecScreen.clientId.text,
            'client_secret': self.connecScreen.clientSecret.text
            })
        headers = {
            'Content-type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
            }

        UrlRequest(
            url         = self._tokenURL.format(baseURL=self._baseURLProd if self.production else self._baseURLDev),
            req_body    = params,
            req_headers = headers,
            on_error    = self.tokenFailure,
            on_failure  = self.tokenFailure,
            on_progress = None,
            on_redirect = None,
            on_success  = self.gotToken,
            timeout     = 5,
            )

    def gotToken(self, request, result):
        print('HMS: Got token')
        self._token = result
        self._tokenSuccessCallback()

    def tokenFailure(self, request, result):
        self._tokenFailCallback()

    def findNext(self):
        print('HMS: Find next meeting')

        headers = {
            'Content-type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
            'Authorization': '{} {}'.format(self._token['token_type'], self._token['access_token'])
            }

        UrlRequest(
            url         = self._meetingNextURL.format(baseURL=self._baseURLProd if self.production else self._baseURLDev),
            req_body    = None,
            req_headers = headers,
            on_error    = None,
            on_failure  = None,
            on_progress = None,
            on_redirect = None,
            on_success  = self.foundNext,
            timeout     = 5,
            )

    def foundNext(self, request, result):
        print('HMS: Found next meeting')
        self._meetinId = result['id']
        self.checkInScreen.updateTitle(result['title'])
        self._resetStatusMessage()
        self.updateCheckInCounts(result)
        self.startRFID()

    def _resetStatusMessage(self, *args):
        self.checkInScreen.statusMessage = self._defaultStatusMessage

    def startRFID(self):
        # start checking RFID's
        self.rfid.startRFIDRead()
        self.eventCheckRFID = Clock.schedule_interval(self.checkForRFID, 0.5)
        # start update counts every 10 sec
        self.eventUpdateCounts = Clock.schedule_interval(self.updateCounts, 5)

    def stopRFID(self):
        self.rfid.stopRFIDRead()
        try:
            self.eventCheckRFID.cancel()
            self.eventUpdateCounts.cancel()
        except:
            pass

    def updateCheckInCounts(self, counts):
        self.checkInScreen.currentMembers = str(counts['currentMembers'])
        self.checkInScreen.votingMembers = str(counts['votingMembers'])
        self.checkInScreen.quorum = str(counts['quorum'])
        self.checkInScreen.attendees = str(counts['attendees'])
        self.checkInScreen.proxies = str(counts['proxies'])
        self.checkInScreen.representedProxies = str(counts['representedProxies'])
        self.checkInScreen.checkInCount = str(counts['checkInCount'])
        self.checkInScreen.quorumMetState = True if counts['checkInCount'] >= counts['quorum'] else False


    def updateCounts(self, *args):
        headers = {
          'Content-type': 'application/x-www-form-urlencoded',
          'Accept': 'application/json',
          'Authorization': '{} {}'.format(self._token['token_type'], self._token['access_token'])
          }

        UrlRequest(
            url         = self._meetingURL.format(baseURL=self._baseURLProd if self.production else self._baseURLDev, meeting=self._meetinId),
            req_body    = None,
            req_headers = headers,
            on_error    = None,
            on_failure  = None,
            on_progress = None,
            on_redirect = None,
            on_success  = self.newCounts,
            timeout     = 5,
            )

    def newCounts(self, request, result):
        self.updateCheckInCounts(result)

    def checkForRFID(self, *args):
        try:
            uid = self.rfid.qRFID.get_nowait()
        except Queue.Empty:
            pass
        else:
            self.checkInScreen.statusMessage = 'Checking Card'
            params = urllib.urlencode({
                'rfidSerial': uid,
                })
            headers = {
                'Content-type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
                'Authorization': '{} {}'.format(self._token['token_type'], self._token['access_token'])
                }

            UrlRequest(
                url         = self._meetingCheckInRfidURL.format(baseURL=self._baseURLProd if self.production else self._baseURLDev, meeting=self._meetinId),
                req_body    = params,
                req_headers = headers,
                on_error    = self.checkInError,
                on_failure  = self.checkInFailure,
                on_progress = None,
                on_redirect = self.checkInRedirect,
                on_success  = self.checkInSuccess,
                timeout     = 5,
                )

    def checkInError(self, request, result):
        print("HMS: Check-in Error")
        print(result)
        self.checkInScreen.statusMessage('Check-in Error')
        Clock.schedule_once(self._resetStatusMessage, 2)

    def checkInFailure(self, request, result):
        print("HMS: Check-in Failure")
        # print(result)
        if ('errors' in result):
            if ('rfidSerial' in result['errors']):
                # this will be a validation error
                self.checkInScreen.statusMessage = result['errors']['rfidSerial'][0]
            else:
                self.checkInScreen.statusMessage = result['errors'][0]['detail']
        Clock.schedule_once(self._resetStatusMessage, 2)

    def checkInRedirect(self, request, result):
        print("HMS: Check-in Redirect")
        print(result)
        self.checkInScreen.statusMessage('Check-in Redirect')
        Clock.schedule_once(self._resetStatusMessage, 2)

    def checkInSuccess(self, request, result):
        print("HMS: Check-in Success")
        # print(result)
        try:
            self.checkInScreen.statusMessage = "{} - {}".format(result['checkInUser']['name'], result['checkInUser']['message'])
        except KeyError:
            print("Key Error")
        self.updateCheckInCounts(result)
        Clock.schedule_once(self._resetStatusMessage, 2)

hms = HMS();

class ScreenSwitcher(ScreenManager):
    #The screens can be added on the __init__ method like this or on the .kv file
    def __init__(self, **kwargs):
        super(ScreenSwitcher, self).__init__(**kwargs)
        self.add_widget(ConnectScreen())
        self.add_widget(CheckInScreen())

# TopBar Digital Clock
class ClockLabel(Label):
    def __init__(self, **kwargs):
        super(ClockLabel, self).__init__(**kwargs)
        Clock.schedule_interval(self.update, 1)

    def update(self, *args):
        self.text = time.strftime('%H:%M:%S')

#Can be moved to another file, but needs to be imported
class ConnectScreen(Screen):
    clientId = ObjectProperty(None)
    clientSecret = ObjectProperty(None)

    def __init__(self, **kwargs):
        super(ConnectScreen, self).__init__(**kwargs)
        self.clientId.text = hms.clientId
        self.clientSecret.text = hms.clientSecret
        hms.connecScreen = self

    def connectBtn(self):
        self.btn.text = "Connecting"
        self.btn.disabled = True
        print('Connecting')
        # get token
        hms.production = self.prodSwitch.active
        hms.getToken(self.connectSuccess, self.connectFail)

    def connectSuccess(self):
        print('Connect Success')
        # get next meeting
        hms.findNext()
        self.parent.current = 'checkIn'

    def connectFail(self):
        print('Failed to get Token')
        self.btn.text = "Failed to get Token"
        self.btn.disabled = False

#Can be moved to another file, but needs to be imported
class CheckInScreen(Screen):
    currentMembers = StringProperty('?')
    votingMembers = StringProperty('?')
    quorum = StringProperty('?')
    attendees = StringProperty('?')
    proxies = StringProperty('?')
    representedProxies = StringProperty('?')
    checkInCount = StringProperty('?')
    quorumMetState = BooleanProperty(False)
    statusMessage = StringProperty('')

    def __init__(self, **kwargs):
        super(CheckInScreen, self).__init__(**kwargs)
        hms.checkInScreen = self

    def on_enter(self):
        self.parent.parent.ids.title.text = 'Finding Next Meeting'

    def on_leave(self):
        hms.stopRFID()

    def updateTitle(self, title):
        self.parent.parent.ids.title.text = title

class MeetingCheckInApp(App):
    def on_stop(self, *args):
        hms.stopRFID()

if __name__ == "__main__":
    Window.size = (800, 480)
    try:
        MeetingCheckInApp().run()
    except KeyboardInterrupt:
        hms.stopRFID()
        MeetingSignInApp().stop()
