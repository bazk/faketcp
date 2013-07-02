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

class Socket(object):
    WINSIZE = 8

    def __init__(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.seq = random.randint(0, 65535)
        self.ack = 0
        self.win = self.WINSIZE
        self.remote_win = 0

        self.connected = False
        self.address = None

        self.connections = []

        self.cv = threading.Condition()

    def bind(self, address):
        if self.connected:
            raise Exception('already connected')

        self._socket.bind(address)

    def connect(self, address):
        if self.connected:
            raise Exception('already connected')

        syn = Packet(flags=Packet.FLAG_SYN)
        self.send_packet(syn, address)

        response, response_addr = self.recv_packet()

        if ((response.flags & Packet.FLAG_ACK) != 0) and ((response.flags & Packet.FLAG_SYN) != 0):
            self.ack = response.seq + 1

            ack = Packet(flags=(Packet.FLAG_ACK))
            self.send_packet(ack, response_addr)

            self.connected = True
            self.address = response_addr

    def listen(self):
        if self.connected:
            raise Exception('already connected')

        packet, addr = self.recv_packet()

        if (packet.flags & Packet.FLAG_SYN) != 0:
            conn = Socket()
            conn.bind(('', 0))
            conn.address = addr
            conn.ack = packet.seq + 1
            syn_ack = Packet(flags=(Packet.FLAG_SYN | Packet.FLAG_ACK))
            conn.send_packet(syn_ack, addr)

            ack, ack_addr = conn.recv_packet()

            if (ack.flags & Packet.FLAG_ACK) != 0:
                conn.ack = packet.seq + 1
                conn.connected = True
                conn.address = ack_addr
                self.connections.append(conn)

    def accept(self):
        if self.connected:
            raise Exception('already connected')

        if len(self.connections) == 0:
            return None

        conn = self.connections.pop(0)
        return (conn, conn.address)

    def recv(self, bufsize, **kwargs):
        if not self.connected:
            raise Exception('not connected')

        (packet, addr) = self.recv_packet()
        return packet.payload

    def send(self, string, **kwargs):
        if not self.connected:
            raise Exception('not connected')

        self.cv.acquire()
        while self.remote_win <= 0:
            self.cv.wait()

        self.remote_win -= 1
        self.cv.release()

        packet = Packet(payload=string)
        self.send_packet(packet, self.address)

    def close(self):
        self.connected = False
        self._socket.close()

    def send_packet(self, packet, address):
        packet.win = self.win
        packet.seq = self.seq
        self.seq += 1
        packet.ack = self.ack
        self._socket.sendto(packet.to_data(), address)

    def recv_packet(self):
        data, addr = self._socket.recvfrom(Packet.BUFSIZ)
        packet = Packet.from_data(data)
        self.cv.acquire()
        self.remote_win = packet.win
        self.cv.notify()
        self.cv.release()
        return (packet, addr)

class ChecksumError(Exception):
    pass

class Packet(object):
    FLAG_ACK = 0x1
    FLAG_SYN = 0x2

    BUFSIZ = 256

    def __init__(self, seq=0, ack=0, flags=0, win=0, payload=''):
        self.seq = seq
        self.ack = ack
        self.flags = flags
        self.win = win
        self.checksum = 0
        self.payload = payload

    def __str__(self):
        return str((self.seq, self.ack, self.flags, \
            self.win, self.checksum, self.payload))

    @staticmethod
    def from_data(data):
        packet = Packet()

        packet.seq, packet.ack, packet.flags, packet.win, \
          packet.checksum = struct.unpack('!IIHHH', data[0:14])
        packet.payload = data[14:]

        if packet.calculate_checksum(data[0:14]) != 0:
            raise ChecksumError('packet header: 0x' + data[0:14].encode('hex'))

        return packet

    def to_data(self):
        header = struct.pack('!IIHH', self.seq, self.ack, self.flags, self.win)
        checksum = struct.pack('!H', self.calculate_checksum(header))
        return header + checksum + self.payload

    def calculate_checksum(self, data):
        def carry_around_add(a, b):
            c = a + b
            return (c & 0xffff) + (c >> 16)

        checksum = 0x0000

        for word in struct.unpack('!' + 'H' * (len(data) / 2), data):
            checksum = carry_around_add(checksum, word)

        return (checksum ^ 0xffff)