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

import unittest
import faketcp
import struct


class TestPacket(unittest.TestCase):
    def setUp(self):
        # forge a packet
        self.packet = faketcp.Packet()
        self.packet.seq = 0x01c0f1cc
        self.packet.ack = 0x00000ca1
        self.packet.flags = 0x0020
        self.packet.win = 0x0081
        self.packet.payload = 'The quick brown fox jumps over the lazy dog'

    def test_assemble_disassemble(self):
        # send
        data = self.packet.to_data()

        # receive
        p = faketcp.Packet.from_data(data)
   
        self.assertEqual(p.seq, self.packet.seq, 'incorrect seq value')
        self.assertEqual(p.ack, self.packet.ack, 'incorrect ack value')
        self.assertEqual(p.flags, self.packet.flags, 'incorrect flags value')
        self.assertEqual(p.win, self.packet.win, 'incorrect win value')
        self.assertEqual(p.payload, self.packet.payload, 'incorrect payload')

    def test_checksum_fail(self):
        # send
        data = self.packet.to_data()

        # modify packet forcing a checksum fail
        data = data[:13] + struct.pack('!B', 0xff) + data[14:]

        # receive
        with self.assertRaises(faketcp.ChecksumError):
            p = faketcp.Packet.from_data(data)


class TestBuffer(unittest.TestCase):
    def setUp(self):
        self.buffer = faketcp.Buffer()

    def test_remaining_size(self):
        self.assertEqual(self.buffer.remaining, self.buffer.BUFSIZ, 'wrong initial remaining size')
        self.buffer.push('test words')
        self.assertEqual(self.buffer.remaining, self.buffer.BUFSIZ - 10, 'wrong buffer remaining size')
        self.assertEqual(self.buffer.pop(5), 'test ', 'pop failed')
        self.assertEqual(self.buffer.remaining, self.buffer.BUFSIZ - 5, 'wrong buffer remaining size (%d)' % self.buffer.remaining)
        self.buffer.push('house')
        self.assertEqual(self.buffer.remaining, self.buffer.BUFSIZ - 10, 'wrong buffer remaining size (%d)' % self.buffer.remaining)
        res = self.buffer.pop(10)
        self.assertEqual(res, 'wordshouse', 'pop failed (%s)' % res)