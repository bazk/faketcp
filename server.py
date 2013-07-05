#!/usr/bin/env python2
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

import faketcp
import socket

if __name__=="__main__":
    HOST = ''
    PORT = 50007

    s = faketcp.Socket()
    s.bind((HOST, PORT))
    s.listen()

    while True:
        print 'waiting new connection...'
        conn, addr = s.accept()
        print 'connected by', addr

        print 'waiting data...'
        data = conn.recv(1024)
        print data

        if data:
            print 'sending data back'
            conn.send(data)
            print 'data sent'

        print 'closing connection'
        conn.close()
        print 'connection closed'