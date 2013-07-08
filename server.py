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
        print 'Listening for new connection on port ', PORT, '...'
        conn, addr = s.accept()

        print 'Connection estabilished (', addr, ').'

        while True:
            try:
                conn.recv(1024)
            except faketcp.NotConnected:
                break

        # print 'Waiting for packet number 1...'
        # data = conn.recv(1024)
        # print 'Received packet number 1: ', data

        # print 'Waiting for packet number 2...'
        # data = conn.recv(1024)
        # print 'Received packet number 2: ', data

        # print 'Waiting for packet number 3...'
        # data = conn.recv(1024)
        # print 'Received packet number 3: ', data

        # print 'Sending response packet number 1...'
        # conn.send('this is the response packet number 1')

        # print 'Waiting for packet number 4...'
        # data = conn.recv(1024)
        # print 'Received packet number 4: ', data

        #conn.close()