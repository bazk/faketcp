# -*- coding: utf-8 -*-
#
# This file is part of faketcp.
#
# faketcp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# trooper-simulator is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with faketcp. If not, see <http://www.gnu.org/licenses/>.

import socket
import struct
import random
import threading
import errno
import collections
import logging

# setup logging
__log__ = logging.getLogger(__name__)

# initialize random number generator
random.seed()

class State:
    """ Enumeration of all possible states for a socket. """
    CLOSED = 0
    LISTEN = 1
    SYN_SENT = 2
    SYN_RECV = 3
    ESTABLISHED = 4

class Flags:
    """ Enumeration of flags for the datagrams. """
    FLAG_ACK = 0x1
    FLAG_SYN = 0x2
    FLAG_NACK = 0x4
    FLAG_DATA = 0x8

class ChecksumError(Exception):
    """ Raised when the checksum of a datagram does not match. """
    pass

class NotConnected(Exception):
    """ Raised when a socket method that needs a connection gets called
    before the connection is established. """
    pass

class AlreadyConnected(Exception):
    """ Raised when a socket method that needs an open socket (not connected)
    gets called after a connection is established. """
    pass

class Socket(object):
    """
    Reliable Datagram Protocol Socket
    Usage is like any standard UDP socket.
    """

    BUFFER_SIZE = 16

    def __init__(self, ploss=0.0, pdup=0.0, pdelay=0.0):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.STATE = State.CLOSED

        self.SND_BUFFER = collections.deque(maxlen=self.BUFFER_SIZE)
        self.RCV_BUFFER = collections.deque(maxlen=self.BUFFER_SIZE)

        self.SND_NXT = 0
        self.SND_UNA = 0
        self.SND_RDY = 0
        self.SND_WND = 0
        self.SND_TIMEOUT = 0.4
        self.SND_TIMER = threading.Timer(self.SND_TIMEOUT, self.send_timeout)
        self.ISS = random.randint(0, 65535) # initial send sequence number

        self.RCV_NXT = 0
        self.RCV_UNA = 0
        self.RCV_WND = self.BUFFER_SIZE
        self.IRS = 0     # initial receive sequence number

        self.ACK_PENDING = False
        self.ACK_TIMEOUT = 0.02
        self.ACK_TIMER = threading.Timer(self.ACK_TIMEOUT, self.ack_timeout)

        self.PLOSS = ploss
        self.PDUP = pdup
        self.PDELAY = pdelay

        self.DELAYED_SEND = None

        self.lock = threading.Lock()

        __log__.info(str(self))

    def __str__(self):
        if self.STATE == 0: state = 'CLOSED'
        elif self.STATE == 1: state = 'LISTEN'
        elif self.STATE == 2: state = 'SYN_SENT'
        elif self.STATE == 3: state = 'SYN_RECV'
        elif self.STATE == 4: state = 'ESTABLISHED'
        else: state = 'UNKNOWN'

        return 'SOCKET(STATE=%s, SND_NXT=%d, SND_UNA=%d, SND_RDY=%d,\
 SND_WND=%d, ISS=%d, RCV_NXT=%d, RCV_UNA=%d, RCV_WND=%d, IRS=%d)' % \
            (state, self.SND_NXT, self.SND_UNA, self.SND_RDY, self.SND_WND,
             self.ISS, self.RCV_NXT, self.RCV_UNA, self.RCV_WND, self.IRS)

    def bind(self, address):
        """ Bind the socket to an specific address. """

        if self.STATE == State.ESTABLISHED:
            raise AlreadyConnected('Cannot bind an already connected socket.')

        self._socket.bind(address)

    def connect(self, address):
        """ Establish a connection to a remote address. """

        if self.STATE == State.ESTABLISHED:
            raise AlreadyConnected(
                'Connection already established, cannot connect again.')

        # Assemble a SYN datagram and send to the remote host
        syn = ReliableDatagram()
        syn.FLAGS = Flags.FLAG_SYN
        syn.WIN = self.RCV_WND
        syn.SEQ = self.ISS
        __log__.info('SEND: ' + str(syn))
        self._socket.sendto(syn.to_data(), address)

        # increase send pointers
        self.SND_RDY += 1
        self.SND_NXT += 1

        # set socket state to SYN_SENT
        self.STATE = State.SYN_SENT

        # wait for the SYN ACK datagram
        while True:
            data, addr = self._recvfrom_wrapper(4096)
            datagram = ReliableDatagram.from_data(data)
            __log__.info('RECV: ' + str(datagram))

            if ((datagram.FLAGS & Flags.FLAG_ACK) != 0) and \
                    ((datagram.FLAGS & Flags.FLAG_SYN) != 0):
                break
            else:
                __log__.warning('Unknown datagram during handshake.')

        # Set RESPONSE ADDRESS as the socket remote address. This is done so
        # the remote host can respond with another socket (bound to another
        # port number)
        self.REMOTE_ADDR = addr

        # synchronize initial receive sequence and window
        self.IRS = datagram.SEQ
        self.SND_WND = datagram.WIN

        # update UNA pointer (because the datagram is an ACK)
        self.SND_UNA = datagram.ACK - self.ISS

        # increase receive pointers
        self.RCV_NXT += 1
        self.RCV_UNA += 1

        # assemble and send an ACK datagram
        ack = ReliableDatagram()
        ack.FLAGS = Flags.FLAG_ACK
        ack.WIN = self.RCV_WND
        ack.SEQ = self.ISS + self.SND_NXT
        ack.ACK = self.IRS + self.RCV_UNA
        __log__.info('SEND: ' + str(ack))
        self._socket.sendto(ack.to_data(), self.REMOTE_ADDR)

        # set the socket state as ESTABLISHED
        self.STATE = State.ESTABLISHED

        # start ACK timer (to send ACKS each 'ACK_TIMEOUT' interval)
        self.ACK_TIMER.start()

    def listen(self):
        """ Put the socket in LISTEN state. """

        if self.STATE == State.ESTABLISHED:
            raise AlreadyConnected(
              'Connection already established, cannot listen.')

        # just set the socket state as listening, nothing else is needed here
        self.STATE = State.LISTEN

    def accept(self):
        """ Block until an connection is established and return a new socket
        relative to that connection. """

        if self.STATE == State.ESTABLISHED:
            raise AlreadyConnected(
              'Connection already established, cannot accept new connections.')

        # loop until receive a SYN
        while True:
            data, addr = self._recvfrom_wrapper(1024)
            datagram = ReliableDatagram.from_data(data)
            __log__.info('RECV: ' + str(datagram))

            if (datagram.FLAGS & Flags.FLAG_SYN) != 0:
                break
            else:
                __log__.warning('Unknown datagram during handshake.')

        # create a new socket to handle the connection
        conn = Socket()

        # bind to a random port
        conn.bind(('', 0))
        conn.REMOTE_ADDR = addr

        # synchronize initial receive sequence and window
        conn.IRS = datagram.SEQ
        conn.SND_WND = datagram.WIN

        # update receive pointers
        conn.RCV_NXT += 1
        conn.RCV_UNA += 1

        # send SYN ACK datagram
        syn_ack = ReliableDatagram()
        syn_ack.FLAGS = Flags.FLAG_SYN | Flags.FLAG_ACK
        syn_ack.WIN = conn.RCV_WND
        syn_ack.SEQ = conn.ISS
        syn_ack.ACK = conn.IRS + conn.RCV_UNA
        __log__.info('SEND: ' + str(syn_ack))
        conn._socket.sendto(syn_ack.to_data(), conn.REMOTE_ADDR)

        # update send pointers
        conn.SND_RDY += 1
        conn.SND_NXT += 1

        # set the connection state as SYN_RECV
        conn.STATE = State.SYN_RECV

        # wait for an ACK
        while True:
            data, addr = conn._recvfrom_wrapper(1024)
            datagram = ReliableDatagram.from_data(data)
            __log__.info('RECV: ' + str(datagram))

            if (datagram.FLAGS & Flags.FLAG_ACK) != 0:
                break
            else:
                __log__.warning('Unknown datagram during handshake.')

        # synchronize window
        conn.SND_WND = datagram.WIN

        # update UNA pointer (because the datagram is an ACK)
        conn.SND_UNA = datagram.ACK - conn.ISS

        # set the socket state as ESTABLISHED
        conn.STATE = State.ESTABLISHED

        # start ACK timer
        conn.ACK_TIMER.start()

        # return the new socket
        return (conn, conn.REMOTE_ADDR)


    def send(self, data, **kwargs):
        """ Send a datagram containing 'data'. """

        if self.STATE != State.ESTABLISHED:
            raise NotConnected('Socket not connected.')

        # assemble the datagram
        datagram = ReliableDatagram()
        datagram.PAYLOAD = data
        datagram.FLAGS = Flags.FLAG_ACK | Flags.FLAG_DATA

        self.lock.acquire()

        # block until there is space on window
        while len(self.SND_BUFFER) >= self.BUFFER_SIZE:
            self.lock.release()
            self.sync()
            self.lock.acquire()

        # set the sequence number
        datagram.SEQ = self.ISS + self.SND_RDY

        # insert into buffer and move 'RDY' pointer
        self.SND_BUFFER.append(datagram)
        self.SND_RDY += 1

        self.lock.release()

        self.sync()

    def recv(self, bufsiz, **kwargs):
        """ Receive a datagram with maximum 'bufsiz' bytes. """

        if self.STATE != State.ESTABLISHED:
            raise NotConnected('Socket not connected.')

        self.lock.acquire()

        # block until a datagram arrives
        while self.RCV_NXT == self.RCV_UNA:
            self.lock.release()
            self.sync(blocking=True)
            self.lock.acquire()

        # remove the datagram from receive buffer
        datagram = self.RCV_BUFFER.popleft()

        # update receive pointers
        self.RCV_WND += 1
        self.RCV_UNA += 1

        self.lock.release()

        # return the datagram payload
        return datagram.PAYLOAD

    def sync(self, blocking=False):
        """
        Synchronize SND_BUFFER and RCV_BUFFER.

        This method tries to receive a datagram (blocking until arrival if
        'blocking' is True) and put into RCV_BUFFER. Then, if there is datagrams
        in SND_BUFFER, it sends one of them.

        Consecutive calls to this method result in a complete flush of
        SND_BUFFER and will acquire all possible datagrams (at the current
        moment) into RCV_BUFFER.
        """

        if self.STATE != State.ESTABLISHED:
            raise NotConnected('Socket not connected.')

        # set internal UDP socket as blocking or not (depending on parameter)
        self._socket.setblocking(blocking)

        avail = True
        try:
            # acquire an UDP datagram (if possible)
            data, addr = self._recvfrom_wrapper(4096)
        except socket.error as (code, msg):
            # if error code is EAGAIN, there is no datagram in UDP buffer
            if code == errno.EAGAIN:
                avail = False
            else:
                raise

        # reset blocking
        self._socket.setblocking(True)

        self.lock.acquire()

        # if a datagram was in fact acquired
        if avail:
            datagram = ReliableDatagram.from_data(data)

            # FIN
            if datagram.SEQ == -1:
                __log__.info('RECV: ' + str(datagram))

                # send FIN ACK
                datagram = ReliableDatagram()
                datagram.SEQ = -1
                datagram.FLAGS = Flags.FLAG_ACK
                self._socket.sendto(datagram.to_data(), self.REMOTE_ADDR)

                # close the connection
                self.lock.release()
                self.close(False)
                self.lock.acquire()

            else:
                # if datagram contains data
                if (datagram.FLAGS & Flags.FLAG_DATA) != 0:
                    if (datagram.SEQ - self.IRS) < self.RCV_NXT:
                        __log__.info('RECV (DUPLICATED): ' + str(datagram))

                    elif (datagram.SEQ - self.IRS) > self.RCV_NXT:
                        __log__.info('RECV (OUT OF ORDER): ' + str(datagram))

                        # send NACK when ACK_TIMEOUT
                        self.send_nack()

                    else:
                        __log__.info('RECV: ' + str(datagram))
                        # push into RCV_BUFFER
                        self.RCV_BUFFER.append(datagram)
                        self.RCV_WND -= 1
                        self.SND_WND = datagram.WIN
                        self.RCV_NXT += 1
                        self.ACK_PENDING = True

                # if datagram has no data, just log it
                else:
                    __log__.info('RECV: ' + str(datagram))

                # process ACK
                if (datagram.FLAGS & Flags.FLAG_ACK) != 0:
                    # remove acknowloged datagrams from SND_BUFFER
                    num_datagrams_acked = datagram.ACK - self.ISS - self.SND_UNA
                    for i in range(num_datagrams_acked):
                        self.SND_BUFFER.popleft()

                    # update UNA pointer and window size
                    self.SND_UNA = datagram.ACK - self.ISS
                    self.SND_WND = datagram.WIN

                    # reset retransmission timer
                    self.SND_TIMER.cancel()
                    self.SND_TIMER = threading.Timer(self.SND_TIMEOUT, self.send_timeout)
                    self.SND_TIMER.start()

                if (datagram.FLAGS & Flags.FLAG_NACK) != 0:
                    # NOTE: when a NACK is received, the ACK information is
                    #       still valid and should be treated here.

                    # remove acknowloged datagrams from SND_BUFFER
                    num_datagrams_acked = datagram.ACK - self.ISS - self.SND_UNA
                    for i in range(num_datagrams_acked):
                        self.SND_BUFFER.popleft()

                    # update UNA pointer and window size
                    self.SND_UNA = datagram.ACK - self.ISS
                    self.SND_WND = datagram.WIN

                    # reset retransmission timer
                    self.SND_TIMER.cancel()
                    self.SND_TIMER = threading.Timer(self.SND_TIMEOUT, self.send_timeout)
                    self.SND_TIMER.start()

                    if self.SND_NXT > self.SND_UNA:
                        __log__.info('RETRANSMISSION STARTED (triggered by NACK)')
                        self.SND_NXT = self.SND_UNA


        # if there is datagrams ready in SND_BUFFER and space in send window
        if (self.SND_RDY > self.SND_NXT) and (self.SND_WND > 0):
            # get the datagram from buffer
            send_datagram = self.SND_BUFFER[self.SND_NXT-self.SND_UNA]

            # set datagram ACK and WIN for synchronization
            send_datagram.ACK = self.IRS + self.RCV_UNA
            send_datagram.WIN = self.RCV_WND

            something_actually_sent = False

            if self.DELAYED_SEND is None and random.uniform(0,1) < self.PDELAY:
                # set datagram as delayed (will be sent in the next sync call)
                __log__.info('SEND (DELAYED): ' + str(send_datagram))
                self.DELAYED_SEND = send_datagram

            elif random.uniform(0,1) < self.PDUP:
                # send the datagram twice
                __log__.info('SEND (DUP): ' + str(send_datagram))
                self._socket.sendto(send_datagram.to_data(), self.REMOTE_ADDR)
                self._socket.sendto(send_datagram.to_data(), self.REMOTE_ADDR)
                something_actually_sent = True

            elif random.uniform(0,1) < self.PLOSS:
                # do not send the datagram
                __log__.info('SEND (LOST): ' + str(send_datagram))

            else:
                # just send the datagram normally
                __log__.info('SEND: ' + str(send_datagram))
                self._socket.sendto(send_datagram.to_data(), self.REMOTE_ADDR)
                something_actually_sent = True

            # send delayed datagram if set in the last sync call
            if something_actually_sent and self.DELAYED_SEND is not None:
                self._socket.sendto(self.DELAYED_SEND.to_data(),
                    self.REMOTE_ADDR)
                self.DELAYED_SEND = None

            # update pointers and window
            self.SND_NXT += 1
            self.SND_WND -= 1

            # reset ACK timer (since ACK is piggybacked in every DATA datagram)
            self.ACK_TIMER.cancel()
            self.ACK_TIMER = threading.Timer(self.ACK_TIMEOUT, self.ack_timeout)
            self.ACK_TIMER.start()

        self.lock.release()

    def send_nack(self):
        """ Send a NACK datagram (no payload). """

        datagram = ReliableDatagram()
        datagram.SEQ = self.ISS + self.SND_RDY
        datagram.ACK = self.IRS + self.RCV_UNA
        datagram.WIN = self.RCV_WND
        datagram.FLAGS = Flags.FLAG_NACK
        __log__.info('SEND: ' + str(datagram))
        self._socket.sendto(datagram.to_data(), self.REMOTE_ADDR)

    def send_ack(self):
        """ Send an ACK datagram (no payload). """

        datagram = ReliableDatagram()
        datagram.SEQ = self.ISS + self.SND_NXT
        datagram.ACK = self.IRS + self.RCV_UNA
        datagram.WIN = self.RCV_WND
        datagram.FLAGS = Flags.FLAG_ACK
        __log__.info('SEND: ' + str(datagram))
        self._socket.sendto(datagram.to_data(), self.REMOTE_ADDR)

    def send_timeout(self):
        """ Callback to SND_TIMER timeout. """

        if self.STATE != State.ESTABLISHED:
            return

        self.lock.acquire()

        # if unacknowledged data exists in SND_BUFFER
        if self.SND_NXT > self.SND_UNA:
            self.SND_NXT = self.SND_UNA
            __log__.info('RETRANSMISSION STARTED (triggered by SND_TIMEOUT)')

        # restart timer
        self.SND_TIMER.cancel()
        self.SND_TIMER = threading.Timer(self.SND_TIMEOUT, self.send_timeout)
        self.SND_TIMER.start()

        self.lock.release()

    def ack_timeout(self):
        """ Callback to ACK_TIMER timeout. """

        if self.STATE != State.ESTABLISHED:
            return

        self.lock.acquire()

        # if ACK pending, send it
        if self.ACK_PENDING:
            self.send_ack()
            self.ACK_PENDING = False

        # reset timer
        self.ACK_TIMER.cancel()
        self.ACK_TIMER = threading.Timer(self.ACK_TIMEOUT, self.ack_timeout)
        self.ACK_TIMER.start()

        self.lock.release()

    def _recvfrom_wrapper(self, bufsiz):
        """ Wrapper for UDP socket recvfrom method that threats the EINTR
        exception. This way we can use timers and alarms without breaking the
        socket. """

        while True:
            try:
                return self._socket.recvfrom(bufsiz)
            except socket.error as (code, msg):
                if code != errno.EINTR:
                    raise

    def close(self, send_fin=True):
        """ Close an established connection. """

        self.lock.acquire()

        if self.STATE == State.ESTABLISHED:
            if send_fin:
                # wait 'til buffers flushes
                while (len(self.SND_BUFFER) > 0) or (len(self.RCV_BUFFER) > 0):
                    self.lock.release()
                    self.sync()
                    self.lock.acquire()

                # stop timers
                self.SND_TIMER.cancel()
                self.ACK_TIMER.cancel()

                # send pending ack
                if self.ACK_PENDING:
                    self.send_ack()
                    self.ACK_PENDING = False

                # send FIN
                datagram = ReliableDatagram()
                datagram.SEQ = -1
                __log__.info('SEND: ' + str(datagram))
                self._socket.sendto(datagram.to_data(), self.REMOTE_ADDR)

                # wait for an FIN ACK
                while True:
                    data, addr = self._recvfrom_wrapper(1024)
                    datagram = ReliableDatagram.from_data(data)

                    if (datagram.SEQ) == -1:
                        __log__.info('RECV: ' + str(datagram))
                        break

            # stop timers (if not stopped already)
            self.SND_TIMER.cancel()
            self.ACK_TIMER.cancel()

        # close the socket
        self.STATE = State.CLOSED
        self._socket.close()

        self.lock.release()

class ReliableDatagram(object):
    """ Representation of a RDP datagram. """

    def __init__(self):
        self.SEQ = 0
        self.ACK = 0
        self.FLAGS = 0x0000
        self.WIN = 0
        self.CHECKSUM = 0
        self.PAYLOAD = ''

    def __str__(self):
        def flags():
            flags = []
            if (self.FLAGS & Flags.FLAG_ACK) != 0:  flags.append('ACK')
            if (self.FLAGS & Flags.FLAG_SYN) != 0:  flags.append('SYN')
            if (self.FLAGS & Flags.FLAG_NACK) != 0: flags.append('NACK')
            if (self.FLAGS & Flags.FLAG_DATA) != 0: flags.append('DATA')
            if self.SEQ == -1:  flags.append('FIN')
            return '|'.join(flags)

        return "(FLAGS=%s  SEQ=%d  ACK=%d  WIN=%d  PAYLOAD='%s')" % \
            (flags(), self.SEQ, self.ACK, self.WIN, self.PAYLOAD)

    @staticmethod
    def from_data(data):
        """ Transforms raw data into a ReliableDatagram. """

        dgram = ReliableDatagram()

        dgram.SEQ, dgram.ACK, dgram.FLAGS, dgram.WIN, \
                dgram.CHECKSUM = struct.unpack('!iiHHH', data[0:14])
        dgram.PAYLOAD = data[14:]

        if dgram.calculate_checksum(data[0:14]) != 0:
            raise ChecksumError('dgram header: 0x' + data[0:14].encode('hex'))

        return dgram

    def to_data(self):
        """ Transforms a ReliableDatagram in raw data. """

        header = struct.pack('!iiHH', self.SEQ, self.ACK, self.FLAGS, self.WIN)
        self.CHECKSUM = struct.pack('!H', self.calculate_checksum(header))
        return header + self.CHECKSUM + self.PAYLOAD

    def calculate_checksum(self, data):
        """ Calculate the checksum of a string of data. """

        def carry_around_add(a, b):
            c = a + b
            return (c & 0xffff) + (c >> 16)

        checksum = 0x0000

        for word in struct.unpack('!' + 'H' * (len(data) / 2), data):
            checksum = carry_around_add(checksum, word)

        return (checksum ^ 0xffff)