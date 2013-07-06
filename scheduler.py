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

import heapq
import signal
import time

class Timer:
    def __init__(self, timeout, callback, *args, **kwargs):
        self.timeout = float(timeout)
        self.callback = callback
        self.args = args
        self.kwargs = kwargs

    def timeout_handler(self):
        self.callback(*self.args, **self.kwargs)

class Scheduler:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Scheduler, cls).__new__(cls, *args, **kwargs)

        return cls._instance

    def __init__(self):
        signal.signal(signal.SIGALRM, self.alarm_handler)
        self.timers = []
        self.last_update = None

    def add_timer(self, timer):
        heapq.heappush(self.timers, (timer.timeout, timer))
        self.update_alarm()

    def update_alarm(self):
        if len(self.timers) == 0:
            signal.alarm(0)
            return

        if self.last_update is None:
            diff = 0
        else:
            diff = time.time() - self.last_update

        new_queue = []
        smallest = None

        while len(self.timers) > 0:
            (timeout, timer) = heapq.heappop(self.timers)
            timeout -= diff

            if timeout <= 0:
                print 'WARNING: overtime (%d)', timeout
                timer.timeout_handler()
            else:
                if smallest is None:
                    smallest = timeout
                heapq.heappush(new_queue, (timeout, timer))


        self.timers = new_queue


        if smallest is None:
            print 'smallest = None, queue=%s' % (self.timers)
            signal.alarm(0)
        else:
            print 'smallest = %f, queue=%s' % (smallest, self.timers)
            signal.setitimer(signal.ITIMER_REAL, smallest)

        self.last_update = time.time()

    def alarm_handler(self, signum, frame):
        if len(self.timers) == 0:
            return

        (timeout, timer) = heapq.heappop(self.timers)
        timer.timeout_handler()
        self.update_alarm()