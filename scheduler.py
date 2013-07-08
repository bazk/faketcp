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

import threading
import heapq
import time

class Timer:
    def __init__(self, timeout, callback, *args, **kwargs):
        self.initial_timeout = float(timeout)
        self.timeout = float(timeout)
        self.callback = callback
        self.args = args
        self.kwargs = kwargs

        self.scheduler = Scheduler()

        self.running = False

    def start(self):
        if self.running:
            return

        self.scheduler.add_timer(self)

    def stop(self):
        if not self.running:
            return

        self.scheduler.remove_timer(self)

    def reset(self):
        self.scheduler.remove_timer(self)
        self.timeout = self.initial_timeout
        self.scheduler.add_timer(self)

    def timeout_handler(self):
        self.callback(*self.args, **self.kwargs)

class Scheduler():
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Scheduler, cls).__new__(cls, *args, **kwargs)

        return cls._instance

    def __init__(self):
        self.timers = []
        self.last_update = None
        self.wait_timeout = 0

        self.thread = threading.Thread(target=self.run)
        self.lock = threading.Lock()
        self.cv = threading.Condition(lock)
        self.exit = False

        self.thread.start()

    def stop(self):
        self.cv.acquire()
        try:
            print 'exit = False'
            self.exit = True
            print 'exit = True'
            self.cv.notify()
        finally:
            self.cv.release()

        self.thread.join()

    def run(self):
        self.cv.acquire()

        while not self.exit:
            print 'exit must be True'

            if self.wait_timeout == 0:
                self.cv.wait()
            else:
                self.cv.wait(timeout=self.wait_timeout)

            self.update_timers()

        self.cv.release()

    def add_timer(self, timer):
        self.cv.acquire()
        try:
            self.cv.notify()
            heapq.heappush(self.timers, (timer.timeout, timer))
            self.cv.notify()
        finally:
            self.cv.release()

    def remove_timer(self, timer):
        self.cv.acquire()

        try:
            for i in range(len(self.timers)):
                if self.timers[i] == timer:
                    del self.timers[i]
                    break

            self.cv.notify()
        finally:
            self.cv.release()

    def update_timers(self):
        if self.last_update is None:
            diff = 0
        else:
            diff = time.time() - self.last_update

        self.last_update = time.time()

        if len(self.timers) == 0:
            self.wait_timeout = 0
            return

        self.last_update = time.time()

        new_queue = []
        smallest = None

        while len(self.timers) > 0:
            (timeout, timer) = heapq.heappop(self.timers)
            timeout -= diff

            if timeout <= 0:
                timer.timeout_handler()
            else:
                if smallest is None:
                    smallest = timeout
                heapq.heappush(new_queue, (timeout, timer))

        self.timers = new_queue

        if smallest is None:
            self.wait_timeout = 0
        else:
            self.wait_timeout = smallest