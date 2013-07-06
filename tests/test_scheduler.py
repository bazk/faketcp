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
import scheduler
import time

class TestScheduler(unittest.TestCase):
    def setUp(self):
        self.man = scheduler.Scheduler()
        self.cb_calls = 0

    def callback(self):
        self.cb_calls += 1

    def test_one_timer(self):
        self.man.add_timer(scheduler.Timer(1, self.callback))
        time.sleep(1)
        time.sleep(1)
        self.assertEquals(self.cb_calls, 1, 'callback not called')

    def test_two_timers(self):
        self.man.add_timer(scheduler.Timer(1, self.callback))
        self.man.add_timer(scheduler.Timer(3, self.callback))
        time.sleep(1)
        time.sleep(1)
        self.assertEquals(self.cb_calls, 1, 'first callback not called')
        time.sleep(1)
        time.sleep(1)
        self.assertEquals(self.cb_calls, 2, 'second callback not called')


    def test_three_timers(self):
        self.man.add_timer(scheduler.Timer(1, self.callback))
        self.man.add_timer(scheduler.Timer(6, self.callback))
        self.man.add_timer(scheduler.Timer(3, self.callback))
        time.sleep(1)
        time.sleep(1)
        self.assertEquals(self.cb_calls, 1, 'first callback not called')
        time.sleep(1)
        time.sleep(1)
        self.assertEquals(self.cb_calls, 2, 'second callback not called')
        time.sleep(1)
        time.sleep(1)
        time.sleep(1)
        self.assertEquals(self.cb_calls, 3, 'third callback not called')

    def test_three_timer_with_simultaneos(self):
        self.man.add_timer(scheduler.Timer(3, self.callback))
        self.man.add_timer(scheduler.Timer(1, self.callback))
        self.man.add_timer(scheduler.Timer(3, self.callback))
        time.sleep(1)
        time.sleep(1)
        self.assertEquals(self.cb_calls, 1, 'first callback not called')
        time.sleep(1)
        time.sleep(1)
        self.assertEquals(self.cb_calls, 3, 'second and third callbacks not called')