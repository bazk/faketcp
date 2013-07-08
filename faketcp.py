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
import atexit

class State:
    CLOSED = 0
    LISTEN = 1
    SYN_SENT = 2
    SYN_RECV = 3
    ESTABLISHED = 4

class Flags:
    FLAG_ACK = 0x1
    FLAG_SYN = 0x2
    FLAG_NACK = 0x4
    FLAG_DATA = 0x8

class ChecksumError(Exception):
    pass

class NotConnected(Exception):
    pass

class Socket(object):
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
        self.SND_TIMEOUT = 0.1
        self.SND_TIMER = threading.Timer(self.SND_TIMEOUT, self.send_timeout)
        self.ISS = random.randint(0, 65535) # initial send sequence number

        self.RCV_NXT = 0
        self.RCV_UNA = 0
        self.RCV_WND = self.BUFFER_SIZE
        self.IRS = 0     # initial receive sequence number

        self.ACK_PENDING = False
        self.NACK_PENDING = False
        self.ACK_TIMEOUT = 0.02
        self.ACK_TIMER = threading.Timer(self.ACK_TIMEOUT, self.ack_timeout)

        self.PLOSS = ploss
        self.PDUP = pdup
        self.PDELAY = pdelay

        self.DELAYED_SEND = None

        self.lock = threading.Lock()

    def __str__(self):
        if self.STATE == 0: state = 'CLOSED'
        elif self.STATE == 1: state = 'LISTEN'
        elif self.STATE == 2: state = 'SYN_SENT'
        elif self.STATE == 3: state = 'SYN_RECV'
        elif self.STATE == 4: state = 'ESTABLISHED'
        else: state = 'UNKNOWN'

        return 'Socket (STATE=%s, SND_NXT=%d, SND_UNA=%d, SND_WND=%d, ISS=%d,\
 RCV_NXT=%d, RCV_UNA=%d, RCV_WND=%d, IRS=%d)' % (state, self.SND_NXT, \
             self.SND_UNA, self.SND_WND, self.ISS, self.RCV_NXT, \
             self.RCV_UNA, self.RCV_WND, self.IRS)

    def bind(self, address):
        if self.STATE == State.ESTABLISHED:
            raise Exception('already connected')

        self._socket.bind(address)

    def connect(self, address):
        if self.STATE == State.ESTABLISHED:
            raise Exception('already connected')

        syn = Segment()
        syn.FLAGS = Flags.FLAG_SYN
        syn.WIN = self.RCV_WND
        syn.SEQ = self.ISS
        print 'SEND: ', str(syn)
        self._socket.sendto(syn.to_data(), address)

        self.SND_RDY += 1
        self.SND_NXT += 1

        self.STATE = State.SYN_SENT
        self.SND_TIMER.start()

        while True:
            data, addr = self._recvfrom_wrapper(4096)
            segment = Segment.from_data(data)
            print 'RECEIVE: ', str(segment)

            if ((segment.FLAGS & Flags.FLAG_ACK) != 0) and ((segment.FLAGS & Flags.FLAG_SYN) != 0):
                break

        self.SND_TIMER.cancel()
        self.SND_TIMER = threading.Timer(self.SND_TIMEOUT, self.send_timeout)
        self.SND_TIMER.start()

        self.SND_UNA = segment.ACK - self.ISS
        self.SND_WND = segment.WIN

        self.REMOTE_ADDR = addr
        self.IRS = segment.SEQ
        self.RCV_NXT += 1
        self.RCV_UNA += 1

        ack = Segment()
        ack.FLAGS = Flags.FLAG_ACK
        ack.WIN = self.RCV_WND
        ack.SEQ = self.ISS + self.SND_NXT
        ack.ACK = self.IRS + self.RCV_UNA
        print 'SEND: ', str(ack)
        self._socket.sendto(ack.to_data(), self.REMOTE_ADDR)

        self.ACK_TIMER.start()
        self.STATE = State.ESTABLISHED

    def listen(self):
        self.STATE = State.LISTEN

    def accept(self):
        if self.STATE == State.ESTABLISHED:
            raise Exception('already connected')

        # loop until receive a SYN
        while True:
            data, addr = self._recvfrom_wrapper(1024)
            segment = Segment.from_data(data)
            print 'RECEIVE: ', str(segment)

            if (segment.FLAGS & Flags.FLAG_SYN) != 0:
                break
            else:
                print 'Unknown segment...'

        conn = Socket()
        conn.bind(('', 0))
        conn.REMOTE_ADDR = addr
        conn.IRS = segment.SEQ
        conn.SND_WND = segment.WIN
        conn.RCV_NXT += 1
        conn.RCV_UNA += 1

        # send syn, ack segment
        syn_ack = Segment()
        syn_ack.FLAGS = Flags.FLAG_SYN | Flags.FLAG_ACK
        syn_ack.WIN = conn.RCV_WND
        syn_ack.SEQ = conn.ISS
        syn_ack.ACK = conn.IRS + conn.RCV_UNA
        print 'SEND: ', str(syn_ack)
        conn._socket.sendto(syn_ack.to_data(), conn.REMOTE_ADDR)

        conn.SND_RDY += 1
        conn.SND_NXT += 1

        conn.STATE = State.SYN_RECV
        conn.SND_TIMER.start()

        # wait for an ACK
        while True:
            data, addr = conn._recvfrom_wrapper(1024)
            segment = Segment.from_data(data)
            print 'RECEIVE: ', str(segment)

            if (segment.FLAGS & Flags.FLAG_ACK) != 0:
                break

        conn.SND_UNA = segment.ACK - conn.ISS
        conn.SND_WND = segment.WIN
        conn.STATE = State.ESTABLISHED

        conn.SND_TIMER.cancel()
        conn.SND_TIMER = threading.Timer(conn.SND_TIMEOUT, conn.send_timeout)
        conn.SND_TIMER.start()

        conn.ACK_TIMER.start()

        return (conn, conn.REMOTE_ADDR)


    def send(self, data, **kwargs):
        if self.STATE != State.ESTABLISHED:
            raise NotConnected('socket not connected')

        segment = Segment()
        segment.PAYLOAD = data
        segment.FLAGS = Flags.FLAG_ACK | Flags.FLAG_DATA

        self.lock.acquire()

        # block until there is space on window
        while len(self.SND_BUFFER) >= self.BUFFER_SIZE:
            self.lock.release()
            self.sync(blocking=True)
            self.lock.acquire()

        segment.SEQ = self.ISS + self.SND_RDY
        self.push_send_buffer(segment)

        self.lock.release()

        self.sync()

    def recv(self, bufsiz, **kwargs):
        if self.STATE != State.ESTABLISHED:
            raise NotConnected('socket not connected')

        segment = None

        while segment is None:
            self.sync(blocking=True)

            self.lock.acquire()
            segment = self.pop_recv_buffer()
            self.lock.release()

        return segment.PAYLOAD

    def sync(self, blocking=False):
        if self.STATE != State.ESTABLISHED:
            raise NotConnected('socket not connected')

        self._socket.setblocking(blocking)

        avail = True
        try:

            data, addr = self._recvfrom_wrapper(4096)
        except socket.error as (code, msg):
            if code == errno.EAGAIN:
                avail = False
            else:
                raise

        self._socket.setblocking(True)

        self.lock.acquire()

        if avail:
            segment = Segment.from_data(data)

            print 'RECEIVE: ', str(segment)

            if segment.SEQ == -1:
                # send FIN ACK
                segment = Segment()
                segment.SEQ = -1
                self._socket.sendto(segment.to_data(), self.REMOTE_ADDR)

                self.lock.release()
                self.close(False)
                self.lock.acquire()

            else:
                if (segment.FLAGS & Flags.FLAG_ACK) != 0:
                    num_segments_acked = segment.ACK - self.ISS - self.SND_UNA
                    for i in range(num_segments_acked):
                        self.SND_BUFFER.popleft()
                    self.SND_UNA = segment.ACK - self.ISS
                    self.SND_WND = segment.WIN
                    self.SND_TIMER.cancel()
                    self.SND_TIMER = threading.Timer(self.SND_TIMEOUT, self.send_timeout)
                    self.SND_TIMER.start()

                if (segment.FLAGS & Flags.FLAG_NACK) != 0:
                    print 'NACK: ', str(segment)

                    num_segments_acked = segment.ACK - self.ISS - self.SND_UNA
                    for i in range(num_segments_acked):
                        self.SND_BUFFER.popleft()
                    self.SND_UNA = segment.ACK - self.ISS
                    self.SND_WND = segment.WIN
                    self.SND_TIMER.cancel()
                    self.SND_TIMER = threading.Timer(self.SND_TIMEOUT, self.send_timeout)
                    self.SND_TIMER.start()

                    send_segment = self.SND_BUFFER[0]
                    send_segment.ACK = self.IRS + self.RCV_UNA
                    send_segment.WIN = self.RCV_WND
                    print 'RETRANS (NACK): ', str(send_segment)
                    self._socket.sendto(send_segment.to_data(), self.REMOTE_ADDR)

                if (segment.FLAGS & Flags.FLAG_DATA) != 0:
                    if (segment.SEQ - self.IRS) == self.RCV_NXT:
                        self.RCV_BUFFER.append(segment)
                        self.RCV_WND -= 1
                        self.SND_WND = segment.WIN
                        self.RCV_NXT += 1
                        self.ACK_PENDING = True

                    elif (segment.SEQ - self.IRS) < self.RCV_NXT:
                        print 'DUP: ', str(segment)

                    else:
                        print 'OUT OR ORDER: ', str(segment)
                        self.NACK_PENDING = True


        if (self.SND_RDY > self.SND_NXT) and (self.SND_WND > 0):
            send_segment = self.SND_BUFFER[self.SND_RDY-1-self.SND_UNA]
            send_segment.ACK = self.IRS + self.RCV_UNA
            send_segment.WIN = self.RCV_WND

            # send delayed segment if set in the last loop
            if self.DELAYED_SEND is not None:
                print 'SEND (DELAYED): ', str(self.DELAYED_SEND)
                self._socket.sendto(self.DELAYED_SEND.to_data(), self.REMOTE_ADDR)
                self.DELAYED_SEND = None

            # set the current segment as delayed (will be sent in the next loop)
            if random.uniform(0,1) < self.PDELAY:
                self.DELAYED_SEND = send_segment

            # send the segment twice
            elif random.uniform(0,1) < self.PDUP:
                print 'SEND (DUPLICATE): ', str(send_segment)
                self._socket.sendto(send_segment.to_data(), self.REMOTE_ADDR)
                self._socket.sendto(send_segment.to_data(), self.REMOTE_ADDR)

            # do not send the segment
            elif random.uniform(0,1) < self.PLOSS:
                print 'SEND (LOST): ', str(send_segment)

            # normal send
            else:
                print 'SEND: ', str(send_segment)
                self._socket.sendto(send_segment.to_data(), self.REMOTE_ADDR)

            self.SND_NXT += 1
            self.SND_WND -= 1

            self.ACK_TIMER.cancel()
            self.ACK_TIMER = threading.Timer(self.ACK_TIMEOUT, self.ack_timeout)
            self.ACK_TIMER.start()

        self.lock.release()

    def push_send_buffer(self, segment):
        self.SND_BUFFER.append(segment)
        self.SND_RDY += 1

    def pop_recv_buffer(self):
        if self.RCV_NXT == self.RCV_UNA:
            return None

        segment = self.RCV_BUFFER.popleft()
        self.RCV_WND += 1
        self.RCV_UNA += 1
        return segment

    def send_nack(self):
        segment = Segment()
        segment.SEQ = self.ISS + self.SND_RDY
        segment.ACK = self.IRS + self.RCV_UNA
        segment.WIN = self.RCV_WND
        segment.FLAGS = Flags.FLAG_NACK
        print 'SEND NACK: ', str(segment)
        self._socket.sendto(segment.to_data(), self.REMOTE_ADDR)

    def send_ack(self):
        segment = Segment()
        segment.SEQ = self.ISS + self.SND_NXT
        segment.ACK = self.IRS + self.RCV_UNA
        segment.WIN = self.RCV_WND
        segment.FLAGS = Flags.FLAG_ACK
        print 'SEND ACK: ', str(segment)
        self._socket.sendto(segment.to_data(), self.REMOTE_ADDR)

    def send_timeout(self):
        if self.STATE != State.ESTABLISHED:
            return

        self.lock.acquire()

        if self.SND_NXT > self.SND_UNA:
            print 'RETRANSMITTING...', self.SND_NXT, self.SND_UNA, self.SND_RDY, self.SND_WND
            self.SND_NXT = self.SND_UNA
            #segment = self.SND_BUFFER[0]
            #segment.ACK = self.IRS + self.RCV_UNA
            #segment.WIN = self.RCV_WND
            #print 'RETRANS: ', str(segment)
            #self._socket.sendto(segment.to_data(), self.REMOTE_ADDR)

        self.SND_TIMER.cancel()
        self.SND_TIMER = threading.Timer(self.SND_TIMEOUT, self.send_timeout)
        self.SND_TIMER.start()

        self.lock.release()

    def ack_timeout(self):
        if self.STATE != State.ESTABLISHED:
            return

        self.lock.acquire()

        if self.ACK_PENDING:
            self.send_ack()
            self.ACK_PENDING = False
        if self.NACK_PENDING:
            self.send_nack()
            self.NACK_PENDING = False

        self.ACK_TIMER.cancel()
        self.ACK_TIMER = threading.Timer(self.ACK_TIMEOUT, self.ack_timeout)
        self.ACK_TIMER.start()

        self.lock.release()

    def _recvfrom_wrapper(self, bufsiz):
        while True:
            try:
                return self._socket.recvfrom(bufsiz)
            except socket.error as (code, msg):
                if code != errno.EINTR:
                    raise

    def close(self, send_fin=True):
        self.lock.acquire()

        if send_fin:
            # wait 'til buffers flushes
            while (len(self.SND_BUFFER) > 0) or (len(self.RCV_BUFFER) > 0):
                self.lock.release()
                self.sync()
                self.lock.acquire()

            # stop timers
            self.SND_TIMER.cancel()
            self.ACK_TIMER.cancel()

            if self.ACK_PENDING:
                self.send_ack()
                self.ACK_PENDING = False

            # send FIN
            segment = Segment()
            segment.SEQ = -1
            print 'SEND FIN: ', str(segment)
            self._socket.sendto(segment.to_data(), self.REMOTE_ADDR)

            # wait for an FIN ACK
            while True:
                data, addr = self._recvfrom_wrapper(1024)
                segment = Segment.from_data(data)

                if (segment.SEQ) == -1:
                    print 'RECEIVE FIN ACK: ', str(segment)
                    break

        # stop timers (if not stopped already)
        self.SND_TIMER.cancel()
        self.ACK_TIMER.cancel()

        # close the socket
        self.STATE = State.CLOSED
        self._socket.close()

        self.lock.release()

    # def send_segment(self):
    #     # copy 'LEN' bytes of data from buffer and move buffer pointer
    #     segment = Segment()
    #     segment.PAYLOAD = self.SND_BUFFER[self.SND_NXT:self.SND_RDY]
    #     segment.SEQ = self.ISS + self.SND_NXT
    #     segment.ACK = self.IRS + self.RCV_UNA
    #     segment.FLAGS = Flags.FLAG_ACK

    #     self.SND_NXT = self.SND_RDY

    #     if self.DELAYED_SEND is not None:
    #         print 'SEND: ', str(self.DELAYED_SEND)
    #         self._socket.sendto(self.DELAYED_SEND.to_data(), self.REMOTE_ADDR)
    #         self.DELAYED_SEND = None

    #     self.RETRANS_QUEUE.append(segment)

    #     if random.uniform(0,1) < self.PLOSS:
    #         return

    #     if random.uniform(0,1) < self.PDELAY:
    #         self.DELAYED_SEND = segment
    #         return

    #     if random.uniform(0,1) < self.PDUP:
    #         self.DELAYED_SEND = segment

    #     print 'SEND: ', str(segment)
    #     self._socket.sendto(segment.to_data(), self.REMOTE_ADDR)

class Segment(object):
    def __init__(self):
        self.SEQ = 0
        self.ACK = 0
        self.FLAGS = 0x0000
        self.WIN = 0
        self.CHECKSUM = 0
        self.PAYLOAD = ''

    def __str__(self):
        return "(SEQ=%d ACK=%d FLAGS=%d WIN=%d '%s')" % (self.SEQ, self.ACK, self.FLAGS, self.WIN, self.PAYLOAD)

    @staticmethod
    def from_data(data):
        segment = Segment()

        segment.SEQ, segment.ACK, segment.FLAGS, segment.WIN, \
                segment.CHECKSUM = struct.unpack('!iiHHH', data[0:14])
        segment.PAYLOAD = data[14:]

        if segment.calculate_checksum(data[0:14]) != 0:
            raise ChecksumError('segment header: 0x' + data[0:14].encode('hex'))

        return segment

    def to_data(self):
        header = struct.pack('!iiHH', self.SEQ, self.ACK, self.FLAGS, self.WIN)
        self.CHECKSUM = struct.pack('!H', self.calculate_checksum(header))
        return header + self.CHECKSUM + self.PAYLOAD

    def calculate_checksum(self, data):
        def carry_around_add(a, b):
            c = a + b
            return (c & 0xffff) + (c >> 16)

        checksum = 0x0000

        for word in struct.unpack('!' + 'H' * (len(data) / 2), data):
            checksum = carry_around_add(checksum, word)

        return (checksum ^ 0xffff)