"""SAM | 2026-10-21 +08:00 | Bounded MQTT3.1.1 loopback test fixture, NOT a deployment broker.
Only clean CONNECT, exact-topic QoS1 SUBSCRIBE/PUBLISH/PUBACK and DISCONNECT.
No persistent sessions, TLS/auth, retained messages, wildcards, QoS2 or retransmit.
"""
import socket
import socketserver
import struct
import threading

MAX_PACKET=16384

def exact(sock,n):
    data=b''
    while len(data)<n:
        part=sock.recv(n-len(data))
        if not part:raise EOFError()
        data+=part
    return data

def packet(sock):
    kind=exact(sock,1)[0];size=0;factor=1
    for _ in range(4):
        value=exact(sock,1)[0];size+=(value&127)*factor
        if size>MAX_PACKET:raise ValueError('oversized test packet')
        if not value&128:return kind,exact(sock,size)
        factor*=128
    raise ValueError('invalid remaining length')

def wire(kind,body):
    if len(body)>MAX_PACKET:raise ValueError('oversized test packet')
    n=len(body);length=b''
    while True:
        digit=n%128;n//=128;length+=bytes([digit|(128 if n else 0)])
        if not n:break
    return bytes([kind])+length+body

def string(value):
    data=value.encode('utf-8')
    if not data or len(data)>1024 or '\x00' in value:raise ValueError('invalid test string')
    return struct.pack('!H',len(data))+data

def take_string(body):
    if len(body)<2:raise ValueError('short string')
    n=int.from_bytes(body[:2],'big')
    if not 0<n<=1024 or len(body)<n+2:raise ValueError('invalid string')
    value=body[2:2+n].decode('utf-8')
    if '\x00' in value:raise ValueError('NUL string')
    return value,body[2+n:]

class Handler(socketserver.BaseRequestHandler):
    def send(self,kind,body):
        with self.write_lock:self.request.sendall(wire(kind,body))

    def handle(self):
        self.write_lock=threading.Lock();self.topics=set();self.next_id=1
        self.request.settimeout(5)
        try:
            kind,body=packet(self.request)
            if kind!=0x10 or body[:10]!=b'\x00\x04MQTT\x04\x02\x00\x3c':return
            _,rest=take_string(body[10:])
            if rest:return
            self.send(0x20,b'\x00\x00')
            with self.server.lock:self.server.peers.add(self)
            while True:
                kind,body=packet(self.request)
                if kind==0xe0 and not body:return
                if kind==0x40 and len(body)==2:continue
                if kind==0x82:
                    topic,rest=take_string(body[2:])
                    if len(body)<2 or body[:2]==b'\0\0' or rest!=b'\x01' or '+' in topic or '#' in topic:return
                    with self.server.lock:self.topics.add(topic)
                    self.send(0x90,body[:2]+b'\x01')
                elif kind==0x32:
                    topic,rest=take_string(body)
                    if len(rest)<2 or rest[:2]==b'\0\0' or '+' in topic or '#' in topic:return
                    payload=rest[2:]
                    with self.server.lock:
                        peers=[p for p in self.server.peers if topic in p.topics]
                    for peer in peers:
                        try:
                            with peer.write_lock:
                                pid=peer.next_id;peer.next_id=pid%65535+1
                                peer.request.sendall(wire(0x32,string(topic)+struct.pack('!H',pid)+payload))
                        except OSError:pass
                    self.send(0x40,rest[:2])
                else:return
        except (OSError,EOFError,ValueError):pass
        finally:
            with self.server.lock:self.server.peers.discard(self)

class Broker(socketserver.ThreadingTCPServer):
    daemon_threads=True
    def __init__(self):
        self.lock=threading.Lock();self.peers=set()
        super().__init__(('127.0.0.1',0),Handler)

class Client:
    def __init__(self,port,client_id):
        self.socket=socket.create_connection(('127.0.0.1',port),timeout=3)
        self.next_id=1
        self.socket.sendall(wire(0x10,b'\x00\x04MQTT\x04\x02\x00\x3c'+string(client_id)))
        if packet(self.socket)!=(0x20,b'\x00\x00'):raise ValueError('CONNACK')

    def identifier(self):
        pid=struct.pack('!H',self.next_id);self.next_id=self.next_id%65535+1;return pid

    def subscribe(self,topic):
        pid=self.identifier();self.socket.sendall(wire(0x82,pid+string(topic)+b'\x01'))
        if packet(self.socket)!=(0x90,pid+b'\x01'):raise ValueError('SUBACK')

    def publish(self,topic,payload):
        pid=self.identifier();self.socket.sendall(wire(0x32,string(topic)+pid+payload.encode('utf-8')))
        return packet(self.socket)==(0x40,pid)

    def receive(self,timeout=3):
        self.socket.settimeout(timeout)
        try:
            kind,body=packet(self.socket)
            if kind!=0x32:raise ValueError('expected QoS1 publish')
            topic,rest=take_string(body)
            if len(rest)<2:raise ValueError('short publish')
            self.socket.sendall(wire(0x40,rest[:2]))
            return topic,rest[2:].decode('utf-8')
        finally:self.socket.settimeout(3)

    def close(self):
        try:self.socket.sendall(wire(0xe0,b''))
        except OSError:pass
        self.socket.close()
