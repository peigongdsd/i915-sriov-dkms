"""Execute only the original CPUID classifier, stubbing library/log helpers.

This is isolated CPU emulation, not a Windows driver load or GPU test.
No bytes of the extracted driver are modified.
"""
from pathlib import Path
import json,struct,hashlib
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
from unicorn.x86_const import *

root=Path(__file__).resolve().parents[2]
binary=root/'windows/extracted/9033/Graphics/igdkmdn64.sys'
assert hashlib.sha256(binary.read_bytes()).hexdigest() == '2969ef18daf397b43353dd4ff465f52a8107fc1a612eab4a8cc2703dee919a4d', 'Unexpected driver image'
p=pefile.PE(str(binary));base=p.OPTIONAL_HEADER.ImageBase
image=p.get_memory_mapped_image()
obj=0x10000000;stack=0x20000000;stop=0x30000000

def run(vendor,management,nested,brand='INTEL CORE'):
    u=Uc(UC_ARCH_X86,UC_MODE_64)
    u.mem_map(base,(len(image)+0xfff)&~0xfff);u.mem_write(base,image)
    u.mem_map(obj,0x100000);u.mem_map(stack,0x100000);u.mem_map(stop,0x1000)
    u.mem_write(obj+0x49370,brand.encode()+b'\0')
    rsp=stack+0x80000-8;u.mem_write(rsp,struct.pack('<Q',stop))
    u.reg_write(UC_X86_REG_RSP,rsp);u.reg_write(UC_X86_REG_RCX,obj)
    leaves=[]
    def cstring(addr): return bytes(u.mem_read(addr,256)).split(b'\0')[0]
    def ret(value=0):
        sp=u.reg_read(UC_X86_REG_RSP);target=struct.unpack('<Q',u.mem_read(sp,8))[0]
        u.reg_write(UC_X86_REG_RAX,value);u.reg_write(UC_X86_REG_RSP,sp+8);u.reg_write(UC_X86_REG_RIP,target)
    def hook(u,address,size,_):
        rva=address-base
        if address==stop:u.emu_stop();return
        if rva==0x4c58fb:
            dst=u.reg_read(UC_X86_REG_RCX);src=u.reg_read(UC_X86_REG_R8);count=u.reg_read(UC_X86_REG_R9)
            # Imported strncpy_s; destination size is 13 and count is 12 here.
            raw=bytes(u.mem_read(src,count)).split(b'\0')[0]
            u.mem_write(dst,raw+b'\0');ret();return
        if rva==0x4c5901:
            hay=u.reg_read(UC_X86_REG_RCX);needle=u.reg_read(UC_X86_REG_RDX)
            idx=cstring(hay).find(cstring(needle));ret(hay+idx if idx>=0 else 0);return
        if rva in (0x35ca30,0x5b49b0):ret();return
        if bytes(u.mem_read(address,2))==b'\x0f\xa2':
            leaf=u.reg_read(UC_X86_REG_EAX);leaves.append(hex(leaf))
            eax=ebx=ecx=edx=0
            if leaf==1:ecx=(1<<31) if vendor else 0
            elif leaf==0x40000000:
                eax=0x4000000a
                raw=(vendor or '').encode().ljust(12,b'\0')[:12]
                ebx,ecx,edx=struct.unpack('<III',raw)
            elif leaf==0x80000000:eax=0x80000008
            elif leaf==0x40000003:ebx=(1<<12)|1 if management else 0
            elif leaf==0x40000004:eax=1<<12 if nested else 0
            for reg,val in [(UC_X86_REG_EAX,eax),(UC_X86_REG_EBX,ebx),(UC_X86_REG_ECX,ecx),(UC_X86_REG_EDX,edx)]:u.reg_write(reg,val)
            u.reg_write(UC_X86_REG_RIP,address+2)
    u.hook_add(UC_HOOK_CODE,hook)
    u.emu_start(base+0xb680,stop+1,count=10000)
    state,vendor_id=struct.unpack('<II',u.mem_read(obj+0xe98,8))
    assert u.reg_read(UC_X86_REG_RIP)==stop
    return dict(vendor=vendor,management=management,nested=nested,brand=brand,state_e98=state,vendor_e9c=vendor_id,cpuid_leaves=leaves)

results=[run('',False,False),run('KVMKVMKVM',False,False),run('Microsoft Hv',False,False),run('Microsoft Hv',True,False),run('Microsoft Hv',True,True),run('Microsoft Hv',True,True,'AMD RYZEN')]
out=dict(binary=str(binary),sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),classifier_rva='0xb680',method='original code in isolated Unicorn; helper calls stubbed; not a Windows/GPU execution',results=results)
(root/'windows/analysis/9033-classifier-emulation.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
