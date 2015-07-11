#!/usr/bin/env python
# -*- coding: utf-8 -*-

# based on
# https://gist.github.com/voorloopnul/415cb75a3e4f766dc590#file-proxy-py

import socket
import select
import time
import datetime

import sys
import os
import functools
#from gevent import socket
#from gevent.server import StreamServer


from signal import signal, SIGPIPE, SIG_DFL
signal(SIGPIPE,SIG_DFL)

from logging import getLogger, basicConfig
logger = getLogger(__name__)
logcfg = {
   "format": "%(asctime)s.%(msecs).03d %(process)d %(thread)x %(levelname).4s;%(module)s(%(lineno)d/%(funcName)s) %(message)s",
   #"format": "%(message)s",
   "datefmt": "%Y/%m/%dT%H:%M:%S",
   "level": 10,
   "stream": sys.stderr,
}
basicConfig(**logcfg)

def ctrl_less(s):
    return ''.join([chr(x) if x > 31 else '0x{0:0>2x}'.format(x) for x in map(ord,list(s)) ])

def traclog( f ):
    @functools.wraps(f)
    def _f(*args, **kwargs):
        logger.debug("ENTER:{0} {1}".format( f.__name__, kwargs if kwargs else args))
        result = f(*args, **kwargs)
        logger.debug("RETRN:{0} {1}".format( f.__name__, result))
        return result
    return _f

class Forward(object):
    def __init__(self):
        self.forward = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
 
    def start(self, host, port):
        try:
            self.forward.connect((host, port))
            return self.forward
        except Exception, e:
            logger.error( e )
            return False
 
class TheServer(object):
    input_list = []
    channel = {}
    sidmap = {}
    status = {}
 
    def __init__(self, host, port, tgthost, tgtport, buffer_size, delay, basedir):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen(200)
        self.tgthost, self.tgtport = tgthost,tgtport
        self.buffer_size, self.delay = buffer_size, delay
        self.dir = basedir

        if not os.path.isdir(self.dir): os.mkdir(self.dir)
 
    def main_loop(self):
        self.input_list.append(self.server)
        while 1:
            time.sleep(self.delay)
            ss = select.select
            inputready, outputready, exceptready = ss(self.input_list, [], [])
            for self.s in inputready:
                if self.s == self.server:
                    self.on_accept()
                    break
 
                self.data = self.s.recv(self.buffer_size)
                if len(self.data) == 0:
                    self.on_close()
                    break
                else:
                    self.on_recv()
 
    def on_accept(self):
        forward = Forward().start(self.tgthost, self.tgtport)
        clientsock, clientaddr = self.server.accept()
        if forward:
            logger.info(  "{0} has connected".format(clientaddr) )
            self.input_list.append(clientsock)
            self.input_list.append(forward)
            self.channel[clientsock] = forward
            self.channel[forward] = clientsock
            _sidbase="{0}_{1}_{2}_{3}".format(self.tgthost,self.tgtport,clientaddr[0],clientaddr[1])
            self.status[_sidbase]={1: "", -1: ""}
            self.sidmap[clientsock] = (_sidbase, 1)
            self.sidmap[forward] = (_sidbase, -1)
        else:
            logger.warn( "Can't establish connection with remote server.\nClosing connection with client side{0}".format(clientaddr))
            clientsock.close()
 
    def on_close(self):
        logger.info( "{0} has disconnected".format(self.s.getpeername()) )
        for i in [-1,1]:
            del self.status[_sidbase][i]
        del self.status[_sidbase]
        self.input_list.remove(self.s)
        self.input_list.remove(self.channel[self.s])
        out = self.channel[self.s]
        self.channel[out].close()
        self.channel[self.s].close()
        del self.channel[out]
        del self.channel[self.s]
        del self.sidmap[out]
        del self.sidmap[self.s]
 
    def on_recv(self):
        _sidbase=self.sidmap[self.s][0]
        _c_or_s=self.sidmap[self.s][1]
        if not self.status[_sidbase][_c_or_s]:
            self.status[_sidbase][-1*_c_or_s]=""
            self.status[_sidbase][_c_or_s]=datetime.datetime.fromtimestamp(time.time()).strftime("%y%m%d_%H%M%S_%f")
        data = self.data
        open("{0}/{1}".format(self.dir,"_".join([_sidbase,self.status[_sidbase][_c_or_s],"c" if _c_or_s==1 else "s"])),"ab").write(data)
        logger.debug( ctrl_less(data.strip()) )
        self.channel[self.s].send(data)
        
def subdic(d,ks):
    return dict([(k,v) for (k,v) in d.items() if k in ks])

def main(opts):
        
        server = TheServer('', **subdic(opts,["port","tgthost", "tgtport", "buffer_size", "delay", "basedir"]))
        try:
            server.main_loop()
        except KeyboardInterrupt:
            logger.info( "Ctrl C - Stopping server" )
            sys.exit(1)

def parsed_opts():
    import optparse
    import os

    opt = optparse.OptionParser()
    opt.add_option("-P", "--prof", default=False, action="store_true", help="get profile [default: %default]" )
    opt.add_option("-L", "--loglevel", default=15, type="int", help="15:info, 10:debug, 5:trace [default: %default]" )
    opt.add_option("-l", "--port", default=21080, type="int", help="listen port [default: %default]" )
    opt.add_option("-t", "--tgthost", default="localhost",  help="target host [default: %default]" )
    opt.add_option("-p", "--tgtport", default=80, type="int", help="target port [default: %default]" )
    opt.add_option("-B", "--buffer_size", default=4096, type="int", help="buffersize [default: %default]" )
    opt.add_option("-D", "--delay", default=0.0001, type="float", help="delay [default: %default]" )
    opt.add_option("-d", "--basedir", default="logs",  help="directory to store data [default: %default]" )
    (opts, args)= opt.parse_args()
    return dict(vars(opts).items() + [("args", args)])

if __name__ == '__main__':
    opts = parsed_opts()
    logger.setLevel(opts['loglevel'])
    if opts['prof']:
      import cProfile
      cProfile.run('main(opts)')
      sys.exit(0)
    main(opts)

