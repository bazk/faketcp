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

if __name__=="__main__":
    HOST = 'localhost'
    PORT = 50007
    s = faketcp.Socket()
    s.connect((HOST, PORT))
    print 'connection estabilished'
    s.send('Hello, world')
    data = s.recv(1024)
    s.close()
    print 'Received', repr(data)