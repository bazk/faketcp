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

class Socket(object):
    def __init__(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def connect(self, address):
        self._socket.connect(address)

    def bind(self, address):
        self._socket.bind(address)

    def listen(self, backlog):
        self._socket.listen(backlog)

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