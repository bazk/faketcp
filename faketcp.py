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
import scheduler
import random
import threading
import errno

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

class ChecksumError(Exception):
    pass

class Socket(object):
    BUFSIZ = 8

    def __init__(self, ploss=0.0, pdup=0.0, pdelay=0.0):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.STATE = State.CLOSED

        self.SND_BUFFER = bytearray(65535)
        self.RCV_BUFFER = bytearray(65535)

        self.SND_NXT = 0 # send next
        self.SND_UNA = 0
        self.SND_RDY = 0
        self.SND_WND = self.BUFSIZ # send window
        self.SND_TIMEOUT = 2.0
        self.SND_TIMER = scheduler.Timer(self.SND_TIMEOUT, self.send_timeout)
        self.ISS = random.randint(0, 65535) # initial send sequence number

        self.RCV_NXT = 0 # receive next
        self.RCV_UNA = 0
        self.RCV_WND = 0 # receive window
        self.IRS = 0     # initial receive sequence number

        self.PLOSS = ploss
        self.PDUP = pdup
        self.PDELAY = pdelay

        self.DELAYED_SEND = None
        self.RETRANS_QUEUE = []

    def __str__(self):
        if self.STATE == 0: state = 'CLOSED'
        elif self.STATE == 1: state = 'LISTEN'
        elif self.STATE == 2: state = 'SYN_SENT'
        elif self.STATE == 3: state = 'SYN_RECV'
        elif self.STATE == 4: state = 'ESTABLISHED'
        else: state = 'UNKNOWN'

        return 'Socket (STATE=%s, SND_NXT=%d, SND_UNA=%d, SND_RDY=%d, SND_WND=%d, ISS=%d,\
 RCV_NXT=%d, RCV_UNA=%d, RCV_WND=%d, IRS=%d)' % (state, self.SND_NXT, \
             self.SND_UNA, self.SND_RDY, self.SND_WND, self.ISS, self.RCV_NXT, \
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
        syn.WIN = self.SND_WND
        syn.SEQ = self.ISS + self.SND_NXT
        print 'SEND: ', str(syn)
        self._socket.sendto(syn.to_data(), address)
        self.SND_RDY += 1
        self.SND_NXT += 1
        print 'connect: sent SYN'

        self.STATE = State.SYN_SENT
        self.SND_TIMER.start()

        while True:
            data, addr = self._recvfrom_wrapper(4096)
            segment = Segment.from_data(data)

            if ((segment.FLAGS & Flags.FLAG_ACK) != 0) and ((segment.FLAGS & Flags.FLAG_SYN) != 0):
                break

        self.SND_TIMER.stop()

        print 'connect: received SYN ACK'
        self.SND_UNA = segment.ACK - self.ISS

        self.REMOTE_ADDR = addr
        self.IRS = segment.SEQ
        self.RCV_NXT += 1
        self.RCV_UNA += 1

        ack = Segment()
        ack.FLAGS = Flags.FLAG_ACK
        ack.WIN = self.SND_WND
        ack.SEQ = self.ISS + self.SND_NXT
        ack.ACK = self.IRS + self.RCV_UNA
        print 'SEND: ', str(ack)
        self._socket.sendto(ack.to_data(), self.REMOTE_ADDR)
        print 'connect: sent ACK'

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

            if (segment.FLAGS & Flags.FLAG_SYN) != 0:
                break
            else:
                print 'Unknown segment...'

        print 'accept: received SYN'

        conn = Socket()
        conn.bind(('', 0))
        conn.REMOTE_ADDR = addr
        conn.IRS = segment.SEQ
        conn.RCV_NXT += 1
        conn.RCV_UNA += 1

        # send syn, ack segment
        syn_ack = Segment()
        syn_ack.FLAGS = Flags.FLAG_SYN | Flags.FLAG_ACK
        syn_ack.WIN = conn.SND_WND
        syn_ack.SEQ = conn.ISS + conn.SND_NXT
        syn_ack.ACK = conn.IRS + conn.RCV_UNA
        print 'SEND: ', str(syn_ack)
        conn._socket.sendto(syn_ack.to_data(), conn.REMOTE_ADDR)
        conn.SND_RDY += 1
        conn.SND_NXT += 1
        print 'connect: sent SYN ACK through a new socket'

        conn.STATE = State.SYN_RECV
        self.SND_TIMER.start()

        # wait for an ACK
        while True:
            data, addr = conn._recvfrom_wrapper(1024)
            segment = Segment.from_data(data)

            if (segment.FLAGS & Flags.FLAG_ACK) != 0:
                break

        self.SND_TIMER.stop()

        print 'listen: received ACK'
        conn.SND_UNA = segment.ACK - conn.ISS
        conn.STATE = State.ESTABLISHED
        self.SND_TIMER.start()

        return (conn, conn.REMOTE_ADDR)

    def recv(self, bufsize, **kwargs):
        if not self.STATE == State.ESTABLISHED:
            raise Exception('not connected')

        if self.RCV_UNA == self.RCV_NXT: # buffer empty
            self.recv_segment()

        data = self.RCV_BUFFER[self.RCV_UNA:self.RCV_NXT]
        self.RCV_UNA = self.RCV_NXT
        return data

    def send(self, string, **kwargs):
        if not self.STATE == State.ESTABLISHED:
            raise Exception('not connected')

        self.SND_RDY += len(string)
        self.SND_BUFFER[self.SND_NXT:self.SND_RDY] = string

        self.send_segment()

    def close(self):
        self.STATE = State.CLOSED
        self._socket.close()

    def send_segment(self):
        # copy 'LEN' bytes of data from buffer and move buffer pointer
        segment = Segment()
        segment.PAYLOAD = self.SND_BUFFER[self.SND_NXT:self.SND_RDY]
        segment.SEQ = self.ISS + self.SND_NXT
        segment.ACK = self.IRS + self.RCV_UNA
        segment.FLAGS = Flags.FLAG_ACK

        self.SND_NXT = self.SND_RDY

        if self.DELAYED_SEND is not None:
            print 'SEND: ', str(self.DELAYED_SEND)
            self._socket.sendto(self.DELAYED_SEND.to_data(), self.REMOTE_ADDR)
            self.DELAYED_SEND = None

        self.RETRANS_QUEUE.append(segment)

        if random.uniform(0,1) < self.PLOSS:
            return

        if random.uniform(0,1) < self.PDELAY:
            self.DELAYED_SEND = segment
            return

        if random.uniform(0,1) < self.PDUP:
            self.DELAYED_SEND = segment

        print 'SEND: ', str(segment)
        self._socket.sendto(segment.to_data(), self.REMOTE_ADDR)

    def recv_segment(self):
        while True:
            data, addr = self._recvfrom_wrapper(4096)
            segment = Segment.from_data(data)

            print 'RECEIVE: ', str(segment)

            if (segment.FLAGS & Flags.FLAG_SYN) != 0:
                print 'WARNING: RECEIVED A SYN AT MIDDLE OF CONNECTION'
                continue

            if (segment.FLAGS & Flags.FLAG_NACK) != 0:
                if len(self.RETRANS_QUEUE) == 0:
                    print 'ERROR: NACK RECEIVED BUT RETRANS QUEUE IS EMPTY'
                else:
                    print 'WARNING: RECEIVED NACK, RESENDING (SEG.SEQ=%d, SEQ.ACK=%d, SND.NXT=%d, SND.UNA=%d)' % (segment.SEQ, segment.ACK, self.SND_NXT, self.SND_UNA)
                    self.SND_NXT = self.SND_UNA
                    resend = self.RETRANS_QUEUE[0]
                    self._socket.sendto(resend.to_data(), self.REMOTE_ADDR)
                    self.SND_TIMER.reset()

            if (segment.SEQ - self.IRS) == self.RCV_NXT:
                LEN = len(segment.PAYLOAD)
                self.RCV_BUFFER[self.RCV_NXT:self.RCV_NXT+LEN] = segment.PAYLOAD
                self.RCV_NXT += LEN

                if (segment.FLAGS & Flags.FLAG_ACK) != 0:
                    self.SND_UNA = segment.ACK - self.ISS
                    self.SND_TIMER.reset()

                    while (len(self.RETRANS_QUEUE) > 0) and (self.RETRANS_QUEUE[0].SEQ <= segment.ACK):
                        del self.RETRANS_QUEUE[0]

                if LEN > 0:
                    # now there is data on the buffer
                    return

            elif (segment.SEQ - self.IRS) < self.RCV_NXT:
                print 'WARNING: DUPLICATED SEGMENT, DISCARDING (SEG.SEQ=%d, RCV_NXT=%d)' % (segment.SEQ, self.RCV_NXT + self.IRS)

            else:
                print 'WARNING: SEGMENT OUT OF ORDER, SENDING NACK (SEG.SEQ=%d, RCV_NXT=%d)' % (segment.SEQ, self.RCV_NXT + self.IRS)

                #self.send_nack()

    def send_nack(self):
        segment = Segment()
        segment.SEQ = self.ISS + self.SND_NXT
        segment.ACK = self.IRS + self.RCV_UNA
        segment.FLAGS = Flags.FLAG_NACK
        print 'SEND: ', str(segment)
        self._socket.sendto(segment.to_data(), self.REMOTE_ADDR)

    def send_timeout(self):
        if self.STATE == State.SYN_SENT:
            # resend SYN
            pass
        elif self.STATE == State.SYN_RECV:
            # resend ACK
            pass
        elif self.STATE == State.ESTABLISHED:
            if len(self.RETRANS_QUEUE) > 0:
                resend = self.RETRANS_QUEUE[0]
                print 'RETRANS: ', str(resend)
                self._socket.sendto(resend.to_data(), self.REMOTE_ADDR)

        self.SND_TIMER.reset()

    def _recvfrom_wrapper(self, bufsiz):
        while True:
            try:
                return self._socket.recvfrom(bufsiz)
            except socket.error as (code, msg):
                if code != errno.EINTR:
                    raise

class Segment(object):
    def __init__(self):
        self.SEQ = 0
        self.ACK = 0
        self.FLAGS = 0x0000
        self.WIN = 0
        self.CHECKSUM = 0
        self.PAYLOAD = ''

    def __str__(self):
        return "(SEQ=%d ACK=%d FLAGS=%d WIN=%d)" % (self.SEQ, self.ACK, self.FLAGS, self.WIN)

    @staticmethod
    def from_data(data):
        segment = Segment()

        segment.SEQ, segment.ACK, segment.FLAGS, segment.WIN, \
                segment.CHECKSUM = struct.unpack('!IIHHH', data[0:14])
        segment.PAYLOAD = data[14:]

        if segment.calculate_checksum(data[0:14]) != 0:
            raise ChecksumError('segment header: 0x' + data[0:14].encode('hex'))

        return segment

    def to_data(self):
        header = struct.pack('!IIHH', self.SEQ, self.ACK, self.FLAGS, self.WIN)
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