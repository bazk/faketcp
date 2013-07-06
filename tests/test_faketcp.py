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


class TestSegment(unittest.TestCase):
    def setUp(self):
        # forge a segment
        self.segment = faketcp.Segment()
        self.segment.SEQ = 0x01c0f1cc
        self.segment.ACK = 0x00000ca1
        self.segment.FLAGS = 0x0020
        self.segment.WIN = 0x0081
        self.segment.PAYLOAD = 'The quick brown fox jumps over the lazy dog'

    def test_assemble_disassemble(self):
        # send
        data = self.segment.to_data()

        # receive
        p = faketcp.Segment.from_data(data)

        self.assertEqual(p.SEQ, self.segment.SEQ, 'incorrect seq value')
        self.assertEqual(p.ACK, self.segment.ACK, 'incorrect ack value')
        self.assertEqual(p.FLAGS, self.segment.FLAGS, 'incorrect flags value')
        self.assertEqual(p.WIN, self.segment.WIN, 'incorrect win value')
        self.assertEqual(p.PAYLOAD, self.segment.PAYLOAD, 'incorrect payload')

    def test_checksum_fail(self):
        # send
        data = self.segment.to_data()

        # modify segment forcing a checksum fail
        data = data[:13] + struct.pack('!B', 0xff) + data[14:]

        # receive
        with self.assertRaises(faketcp.ChecksumError):
            p = faketcp.Segment.from_data(data)