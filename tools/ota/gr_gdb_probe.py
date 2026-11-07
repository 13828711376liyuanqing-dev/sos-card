"""SAM | 2026-10-24 +08:00 | Minimal local RSP transport for a bounded diagnostic call; no flash download/erase commands."""
import socket

def packet(payload):
    return b'$'+payload+b'#'+('%02x'%(sum(payload)&255)).encode()

def unescape(payload):
    out=bytearray();i=0
    while i<len(payload):
        c=payload[i];i+=1
        if c==125:
            if i==len(payload):raise ValueError('RSP_ESCAPE')
            out.append(payload[i]^32);i+=1
        elif c==42:
            if not out or i==len(payload) or payload[i]<29:raise ValueError('RSP_RLE')
            out.extend(bytes([out[-1]])*(payload[i]-29));i+=1
        else:out.append(c)
        if len(out)>1048576:raise ValueError('RSP_RESPONSE_LIMIT')
    return bytes(out)

def checked_payload(payload,checksum):
    if int(checksum,16)!=(sum(payload)&255):raise ValueError('RSP_CHECKSUM')
    return unescape(payload)

class Rsp:
    def __init__(self,port):
        self.s=socket.create_connection(('127.0.0.1',port),timeout=3)
        self.s.settimeout(6)
        self.s.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
    def receive(self):
        while True:
            c=self.s.recv(1)
            if not c:raise ValueError('RSP_CLOSED')
            if c==b'$':break
        data=bytearray()
        while True:
            c=self.s.recv(1)
            if not c:raise ValueError('RSP_CLOSED')
            if c==b'#':break
            data.extend(c)
            if len(data)>1048576:raise ValueError('RSP_PACKET_LIMIT')
        checksum=b''
        while len(checksum)<2:
            b=self.s.recv(2-len(checksum))
            if not b:raise ValueError('RSP_CLOSED')
            checksum+=b
        result=checked_payload(bytes(data),checksum)
        self.s.sendall(b'+')
        return result
    def command(self,command):
        raw=command.encode() if isinstance(command,str) else command
        self.s.sendall(packet(raw))
        return self.receive()
    def interrupt(self):
        self.s.sendall(b'\x03');return self.receive()
    def memory(self,address,size):
        data=bytearray()
        for off in range(0,size,1024):
            n=min(1024,size-off)
            reply=self.command('m%x,%x'%(address+off,n))
            if reply.startswith(b'E') or len(reply)!=2*n:raise ValueError('RSP_MEMORY_READ')
            data.extend(bytes.fromhex(reply.decode()))
        return bytes(data)
    def close(self):
        self.s.close()

def probe_plan(pc,sp,xpsr):
    if xpsr&511 or not xpsr&0x01000000:raise ValueError('PROBE_REQUIRES_THREAD_MODE')
    # RAM_CODE is part of the same signed application. Caller must additionally
    # match its live instruction bytes to the pinned AXF execution section.
    if pc&1 or not (0x202000<=pc<0x26e000 or 0x106000<=pc<0x10b000):
        raise ValueError('PROBE_PC_OUTSIDE_APP')
    if sp&7 or not (0x2000a000<=sp<=0x20040000):raise ValueError('PROBE_STACK_BOUNDS')
    return dict(scratch_start=sp-0x4000,scratch_bytes=0x4000,
                call_sp=sp-0x800,output=sp-0x100,return_pc=pc)
