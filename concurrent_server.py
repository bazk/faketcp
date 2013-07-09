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

import os
import sys
import argparse
import rdp
import logging.config
import config

logging.config.dictConfig(config.LOGGING)

if __name__=="__main__":
    # parse command line arguments
    parser = argparse.ArgumentParser(description='FakeTCP server')
    parser.add_argument('host', metavar='HOST', type=str, default='', nargs='?', help='bind address')
    parser.add_argument('port', metavar='PORT', type=int, default=50007, nargs='?', help='bind port')
    parser.add_argument('--ploss', metavar='PLOSS', type=float, default=0.0, help='probability of datagram loss between 0.0 and 1.0, defaults to 0.0.')
    parser.add_argument('--pdup', metavar='PDUP', type=float, default=0.0, help='probability of datagram duplication between 0.0 and 1.0, defaults to 0.0.')
    parser.add_argument('--pdelay', metavar='PDELAY', type=float, default=0.0, help='probability of datagram delayed (and arriving out of order) between 0.0 and 1.0, defaults to 0.0.')
    args = parser.parse_args()

    # create the RDP socket
    socket = rdp.Socket(ploss=args.ploss, pdup=args.pdup, pdelay=args.pdelay)
    socket.bind((args.host, args.port))
    socket.listen()

    # loop forever waiting incoming connections
    while True:
        print 'Listening for new connection on ', args.host, ':', args.port, '...'
        conn, addr = socket.accept()

        pid = os.fork()

        if (pid < 0):
            raise Exception('Failed to fork process.')

        elif (pid == 0):
            print 'Connection estabilished (', addr, ').'

            # loop forever waiting datagrams
            while True:
                try:
                    conn.recv(1024)
                except rdp.NotConnected:
                    # break when connection closed
                    break

            print 'Connection closed (', addr, ').'
            sys.exit(0)

    # close the listening socket
    socket.close()