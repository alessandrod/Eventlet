import eventlet
from eventlet import debug, hubs, Timeout, spawn_n, greenthread, wsgi, patcher
from eventlet.green import urllib2
from eventlet.websocket import WebSocket
from nose.tools import ok_, eq_, set_trace, raises
from StringIO import StringIO
from unittest import TestCase
from tests.wsgi_test import _TestBase
import logging
import mock
import random

httplib2 = patcher.import_patched('httplib2')


class WebSocketWSGI(object):
    def __init__(self, handler):
        self.handler = handler

    def __call__(self, environ, start_response):
        print environ
        if not (environ.get('HTTP_CONNECTION') == 'Upgrade' and
                environ.get('HTTP_UPGRADE') == 'WebSocket'):
            # need to check a few more things here for true compliance
            start_response('400 Bad Request', [('Connection','close')])
            return []

        sock = environ['eventlet.input'].get_socket()
        ws = WebSocket(sock, environ)
        handshake_reply = ("HTTP/1.1 101 Web Socket Protocol Handshake\r\n"
                           "Upgrade: WebSocket\r\n"
                           "Connection: Upgrade\r\n"
                           "WebSocket-Origin: %s\r\n"
                           "WebSocket-Location: ws://%s%s\r\n\r\n" % (
                                environ.get('HTTP_ORIGIN'),
                                environ.get('HTTP_HOST'),
                                environ.get('PATH_INFO')))
        sock.sendall(handshake_reply)
        try:
            self.handler(ws)
        except socket.error, e:
            if get_errno(e) != errno.EPIPE:
                raise
        # use this undocumented feature of eventlet.wsgi to ensure that it
        # doesn't barf on the fact that we didn't call start_response
        return wsgi.ALREADY_HANDLED

# demo app
import os
import random
def handle(ws):
    """  This is the websocket handler function.  Note that we
    can dispatch based on path in here, too."""
    if ws.path == '/echo':
        while True:
            m = ws.wait()
            if m is None:
                break
            ws.send(m)

    elif ws.path == '/range':
        for i in xrange(10):
            ws.send("msg %d" % i)
            eventlet.sleep(0.1)

    else:
        ws.close()

wsapp = WebSocketWSGI(handle)


class TestWebSocket(_TestBase):

#    def setUp(self):
#        super(_TestBase, self).setUp()
#        self.logfile = StringIO()
#        self.site = Site()
#        self.killer = None
#        self.set_site()
#        self.spawn_server()
#        self.site.application = WebSocketWSGI(handle, 'http://localhost:%s' % self.port)

    TEST_TIMEOUT = 5
    
    def set_site(self):
        self.site = wsapp


    @raises(urllib2.HTTPError)
    def test_incorrect_headers(self):
        try:
            urllib2.urlopen("http://localhost:%s/echo" % self.port)
        except urllib2.HTTPError, e:
            eq_(e.code, 400)
            raise

    def test_incomplete_headers(self):
        headers = dict(kv.split(': ') for kv in [
                "Upgrade: WebSocket",
                #"Connection: Upgrade", Without this should trigger the HTTPServerError
                "Host: localhost:%s" % self.port,
                "Origin: http://localhost:%s" % self.port,
                "WebSocket-Protocol: ws",
                ])
        http = httplib2.Http()
        resp, content = http.request("http://localhost:%s/echo" % self.port, headers=headers)

        self.assertEqual(resp['status'], '400')
        self.assertEqual(resp['connection'], 'close')
        self.assertEqual(content, '')

    def test_correct_upgrade_request(self):
        connect = [
                "GET /echo HTTP/1.1",
                "Upgrade: WebSocket",
                "Connection: Upgrade",
                "Host: localhost:%s" % self.port,
                "Origin: http://localhost:%s" % self.port,
                "WebSocket-Protocol: ws",
                ]
        sock = eventlet.connect(
            ('localhost', self.port))

        fd = sock.makefile('rw', close=True)
        fd.write('\r\n'.join(connect) + '\r\n\r\n')
        fd.flush()
        result = sock.recv(1024)
        fd.close()
        ## The server responds the correct Websocket handshake
        self.assertEqual(result,
                         '\r\n'.join(['HTTP/1.1 101 Web Socket Protocol Handshake',
                                      'Upgrade: WebSocket',
                                      'Connection: Upgrade',
                                      'WebSocket-Origin: http://localhost:%s' % self.port,
                                      'WebSocket-Location: ws://localhost:%s/echo\r\n\r\n' % self.port]))

    def test_sending_messages_to_websocket(self):
        connect = [
                "GET /echo HTTP/1.1",
                "Upgrade: WebSocket",
                "Connection: Upgrade",
                "Host: localhost:%s" % self.port,
                "Origin: http://localhost:%s" % self.port,
                "WebSocket-Protocol: ws",
                ]
        sock = eventlet.connect(
            ('localhost', self.port))

        fd = sock.makefile('rw', close=True)
        fd.write('\r\n'.join(connect) + '\r\n\r\n')
        fd.flush()
        first_resp = sock.recv(1024)
        fd.write('\x00hello\xFF')
        fd.flush()
        result = sock.recv(1024)
        self.assertEqual(result, '\x00hello\xff')
        fd.write('\x00start')
        fd.flush()
        fd.write(' end\xff')
        fd.flush()
        result = sock.recv(1024)
        self.assertEqual(result, '\x00start end\xff')
        fd.write('')
        fd.flush()



    def test_getting_messages_from_websocket(self):
        connect = [
                "GET /range HTTP/1.1",
                "Upgrade: WebSocket",
                "Connection: Upgrade",
                "Host: localhost:%s" % self.port,
                "Origin: http://localhost:%s" % self.port,
                "WebSocket-Protocol: ws",
                ]
        sock = eventlet.connect(
            ('localhost', self.port))

        fd = sock.makefile('rw', close=True)
        fd.write('\r\n'.join(connect) + '\r\n\r\n')
        fd.flush()
        resp = sock.recv(1024)
        headers, result = resp.split('\r\n\r\n')
        msgs = [result.strip('\x00\xff')]
        cnt = 10
        while cnt:
            msgs.append(sock.recv(20).strip('\x00\xff'))
            cnt -= 1
        # Last item in msgs is an empty string
        self.assertEqual(msgs[:-1], ['msg %d' % i for i in range(10)])


class TestWebSocketObject(TestCase):

    def setUp(self):
        self.mock_socket = s = mock.Mock()
        self.environ = env = dict(HTTP_ORIGIN='http://localhost', HTTP_WEBSOCKET_PROTOCOL='ws',
                                  PATH_INFO='test')

        self.test_ws = WebSocket(s, env)

    def test_recieve(self):
        ws = self.test_ws
        ws.socket.recv.return_value = '\x00hello\xFF'
        eq_(ws.wait(), 'hello')
        eq_(ws._buf, '')
        eq_(len(ws._msgs), 0)
        ws.socket.recv.return_value = ''
        eq_(ws.wait(), None)
        eq_(ws._buf, '')
        eq_(len(ws._msgs), 0)


    def test_send_to_ws(self):
        ws = self.test_ws
        ws.send(u'hello')
        ok_(ws.socket.sendall.called_with("\x00hello\xFF"))
        ws.send(10)
        ok_(ws.socket.sendall.called_with("\x0010\xFF"))

    def test_close_ws(self):
        ws = self.test_ws
        ws.close()
        ok_(ws.socket.shutdown.called_with(True))



