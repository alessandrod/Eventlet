__zmq__ = __import__('zmq')
from eventlet import sleep
from eventlet.hubs import trampoline

__patched__ = ['Context', 'Socket']
globals().update(dict([(var, getattr(__zmq__, var))
                       for var in __zmq__.__all__
                       if not (var.startswith('__')
                            or
                              var in __patched__)
                       ]))

class Context(__zmq__.Context):

    def socket(self, socket_type):
        return Socket(self, socket_type)

class Socket(__zmq__.Socket):
            

    def _send_message(self, data, flags=0, copy=True):
        flags |= __zmq__.NOBLOCK
        while True:
            try:
                super(Socket, self)._send_message(data, flags)
                return
            except __zmq__.ZMQError, e:
                if e.errno != EAGAIN:
                    raise
            trampoline(self, write=True)

    def _send_copy(self, data, flags=0, copy=True):
        flags |= __zmq__.NOBLOCK
        while True:
            try:
                super(Socket, self)._send_copy(data, flags)
                return
            except __zmq__.ZMQError, e:
                if e.errno != EAGAIN:
                    raise
            trampoline(self, write=True)

    def _recv_message(self, flags=0):

        flags |= __zmq__.NOBLOCK
        while True:
            try:
                m = super(Socket, self)._recv_message(flags)
                if m:
                    return m
            except __zmq__.ZMQError, e:
                if e.errno != EAGAIN:
                    raise
            trampoline(self, read=True)

    def _recv_copy(self, flags=0):
        flags |= __zmq__.NOBLOCK
        while True:
            try:
                m = super(Socket, self)._recv_copy(flags)
                if m:
                    return m
            except __zmq__.ZMQError, e:
                if e.errno != EAGAIN:
                    raise
            trampoline(self, read=True)



    