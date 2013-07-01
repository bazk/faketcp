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

class Socket(object):
    def __init__(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def connect(self, address):
        self._socket.connect(address)

    def bind(self, address):
        self._socket.bind(address)

    def listen(self, backlog):
        data, addr = self._socket.recvfrom(BUFSIZ)
        packet = Packet.from_data(data)

    def accept(self):
        conn = Connection(self._socket.accept())
        return (conn, conn.addr)

    def recv(self, bufsize, **kwargs):
        return self._socket.recv(bufsize, **kwargs)

    def send(self, string, **kwargs):
        return self._socket.send(string, **kwargs)

    def sendall(self, string, **kwargs):
        return self._socket.sendall(string, **kwargs)

    def close(self):
        self._socket.close()

class Connection(object):
    def __init__(self, conn_addr):
        (self._conn, self._addr) = conn_addr

    @property
    def addr(self):
        return self._addr

    def recv(self, bufsize, **kwargs):
        return self._conn.recv(bufsize, **kwargs)

    def send(self, string, **kwargs):
        return self._conn.send(string, **kwargs)

    def sendall(self, string, **kwargs):
        return self._conn.sendall(string, **kwargs)

    def close(self):
        self._conn.close()


class Packet(object):
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