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

class Socket(object):
    def __init__(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.seq = 0
        self.ack = 0

    def bind(self, address):
        self._socket.bind(address)

    def connect(self, address):
        self.seq = random.randint(0, 65535)

        syn = Packet()
        syn.seq = self.seq
        self.seq += 1
        syn.flags = Packet.FLAG_SYN
        self._socket.sendto(syn.to_data(), address)

        data, addr = self._socket.recvfrom(Packet.BUFSIZ)
        packet = Packet.from_data(data)

        if ((packet.flags & Packet.FLAG_ACK) != 0) and ((packet.flags & Packet.FLAG_SYN) != 0):
            self.ack = packet.seq + 1
            ack = Packet()
            ack.seq = self.seq
            self.seq += 1
            ack.ack = self.ack
            ack.flags = Packet.FLAG_SYN | Packet.FLAG_ACK
            self._socket.sendto(ack.to_data(), addr)

    def listen(self):
        while True:
            data, addr = self._socket.recvfrom(Packet.BUFSIZ)
            packet = Packet.from_data(data)

            if (packet.flags & Packet.FLAG_SYN) != 0:
                self.ack = packet.seq + 1
                self.seq = random.randint(0, 65535)

                syn_ack = Packet()
                syn_ack.seq = self.seq
                self.seq += 1
                syn_ack.ack = self.ack
                syn_ack.flags = Packet.FLAG_SYN | Packet.FLAG_ACK
                self._socket.sendto(syn_ack.to_data(), addr)

                break

    def accept(self):
        data, addr = self._socket.recvfrom(Packet.BUFSIZ)
        packet = Packet.from_data(data)

        if (packet.flags & Packet.FLAG_ACK) != 0:
            conn = Socket()
            conn.ack = packet.seq + 1
            conn.seq = self.seq
            return (conn, addr)

    def recv(self, bufsize, **kwargs):
        pass

    def send(self, string, **kwargs):
        pass

    def sendall(self, string, **kwargs):
        pass

    def close(self):
        pass

class Packet(object):
    FLAG_ACK = 0x1
    FLAG_SYN = 0x2

    BUFSIZ = 256

    def __init__(self):
        self.seq = 0
        self.ack = 0
        self.flags = 0
        self.win = 0
        self.checksum = 0
        self.payload = ''

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
            raise Exception('checksum failed')

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