"""Execute the unmodified 7092 CPUID classifier in an isolated CPU emulator.

This is not Windows, a GPU simulation, or a full driver startup test. Only the
identified routine runs. String/memory library calls, logging and stack-cookie
checking are substituted; CPUID responses and the CPU-brand input are supplied.
"""
from pathlib import Path
import json, struct, hashlib
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import *

root=Path(__file__).resolve().parents[1]
image=root/'extracted/7092/Graphics/igdkmdn64.sys'
pe=pefile.PE(str(image));base=pe.OPTIONAL_HEADER.ImageBase
expected='454624942bf9a79a75fd1bfe6c6a2f8d499aabef45cb4268a1353d527902d098'
assert hashlib.sha256(image.read_bytes()).hexdigest()==expected
obj=0x200000000;stack=0x300000000;stop=0x400000000
cases=[('bare-metal',None,0,False),('KVM','KVMKVMKVM\0\0\0',0,False),
       ('VMware','VMwareVMware',0,False),('Hyper-V child','Microsoft Hv',0,False),
       ('Hyper-V root','Microsoft Hv',0x1001,False),
       ('Nested Hyper-V root','Microsoft Hv',0x1001,True)]
results=[]
for name,vendor,priv,nested in cases:
    u=Uc(UC_ARCH_X86,UC_MODE_64)
    size=(pe.OPTIONAL_HEADER.SizeOfImage+0xfff)&~0xfff
    u.mem_map(base,size);u.mem_write(base,pe.get_memory_mapped_image())
    u.mem_map(obj,0x100000);u.mem_map(stack,0x20000);u.mem_map(stop,0x1000)
    u.mem_write(obj+0x5ac14,b'INTEL CORE I7-1260P\0')
    sp=stack+0x10000-8;u.mem_write(sp,struct.pack('<Q',stop))
    u.reg_write(UC_X86_REG_RSP,sp);u.reg_write(UC_X86_REG_RCX,obj)
    cpuid=[];stubs=[]
    def cstr(addr):
        out=bytearray()
        while len(out)<256:
            v=u.mem_read(addr+len(out),1)[0]
            if not v:return bytes(out)
            out.append(v)
        raise RuntimeError('unterminated string')
    def ret(value=0):
        rsp=u.reg_read(UC_X86_REG_RSP)
        target=struct.unpack('<Q',u.mem_read(rsp,8))[0]
        u.reg_write(UC_X86_REG_RAX,value);u.reg_write(UC_X86_REG_RSP,rsp+8)
        u.reg_write(UC_X86_REG_RIP,target)
    def hook(uc,addr,size,_):
        rva=addr-base
        if addr==stop:uc.emu_stop();return
        if rva in (0x354828,0x35482e,0x24ed10,0x496500):
            stubs.append(hex(rva))
            if rva==0x354828:
                dst=uc.reg_read(UC_X86_REG_RCX);src=uc.reg_read(UC_X86_REG_R8)
                count=uc.reg_read(UC_X86_REG_R9)
                uc.mem_write(dst,bytes(uc.mem_read(src,count)));ret()
            elif rva==0x35482e:
                dst=uc.reg_read(UC_X86_REG_RCX);needle=uc.reg_read(UC_X86_REG_RDX)
                found=cstr(dst).find(cstr(needle));ret(dst+found if found>=0 else 0)
            else:ret()
            return
        if bytes(uc.mem_read(addr,2))==b'\x0f\xa2':
            leaf=uc.reg_read(UC_X86_REG_EAX);sub=uc.reg_read(UC_X86_REG_ECX)
            values=[0,0,0,0]
            if leaf==1:values[2]=(1<<31) if vendor else 0
            elif leaf==0x40000000:
                values=[0x4000000a,*struct.unpack('<III',vendor.encode())]
            elif leaf==0x80000000:values[0]=0x80000004
            elif leaf==0x40000003:values[1]=priv
            elif leaf==0x40000004:values[0]=(1<<12) if nested else 0
            else:raise RuntimeError(f'unexpected CPUID {leaf:x}')
            cpuid.append({'leaf':hex(leaf),'subleaf':hex(sub),'outputs':[hex(x) for x in values]})
            for reg,value in zip((UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX),values):uc.reg_write(reg,value)
            uc.reg_write(UC_X86_REG_RIP,addr+2)
    u.hook_add(UC_HOOK_CODE,hook)
    u.emu_start(base+0xb3a0,stop,count=10000)
    assert u.reg_read(UC_X86_REG_RIP)==stop
    state,vendor_enum=struct.unpack('<II',u.mem_read(obj+0xf28,8))
    results.append({'case':name,'state_f28':state,'vendor_f2c':vendor_enum,
                    'nested_bit_available':nested,'cpuid_calls':cpuid,'stub_rvas':sorted(set(stubs))})
out={'image_sha256':expected,'routine_rva':'0xb3a0','scope':__doc__,'cases':results}
(root/'analysis/7092/classifier-emulation.json').write_text(json.dumps(out,indent=2)+'\n')
for r in results:print(r['case'],r['state_f28'],r['vendor_f2c'],[x['leaf'] for x in r['cpuid_calls']])
