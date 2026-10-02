"""Original 9033 resource parser with synthetic Windows CM resource descriptors.
This tests a conditional startup failure path, not actual guest resource data.
"""
from pathlib import Path
import json,struct,hashlib
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
from unicorn.x86_const import *
root=Path(__file__).resolve().parents[2]
binary=root/'windows/extracted/9033/Graphics/igdkmdn64.sys'
assert hashlib.sha256(binary.read_bytes()).hexdigest() == '2969ef18daf397b43353dd4ff465f52a8107fc1a612eab4a8cc2703dee919a4d', 'Unexpected driver image'
p=pefile.PE(str(binary));base=p.OPTIONAL_HEADER.ImageBase;image=p.get_memory_mapped_image()
obj=0x10000000;stack=0x20000000;stop=0x30000000;resources=0x40000000

def run(platform,state,extra_resource=False,vf_mode=2):
 u=Uc(UC_ARCH_X86,UC_MODE_64)
 for address,size in [(base,(len(image)+0xfff)&~0xfff),(obj,0x100000),(stack,0x100000),(stop,0x1000),(resources,0x1000)]:u.mem_map(address,size)
 u.mem_write(base,image)
 def w32(address,value):u.mem_write(address,struct.pack('<I',value))
 def w64(address,value):u.mem_write(address,struct.pack('<Q',value))
 w32(obj+0x72c,platform);w32(obj+0xe98,state);w32(obj+0xe9c,3);w32(obj+0x45660,vf_mode);w32(obj+0xc9c,1)
 w64(obj+0x1638,resources)
 w32(resources,1);w32(resources+16,2 if extra_resource else 1)
 u.mem_write(resources+20,b'\x03');w64(resources+24,0x80000000);w32(resources+32,0x1000000)
 if extra_resource:
  u.mem_write(resources+40,b'\x03');w64(resources+44,0x100000000);w32(resources+52,0x10000000)
 rsp=stack+0x80000-8;w64(rsp,stop);u.reg_write(UC_X86_REG_RSP,rsp);u.reg_write(UC_X86_REG_RCX,obj)
 calls=[];visited=[]
 def ret(value=0):
  sp=u.reg_read(UC_X86_REG_RSP);target=struct.unpack('<Q',u.mem_read(sp,8))[0]
  u.reg_write(UC_X86_REG_RAX,value);u.reg_write(UC_X86_REG_RSP,sp+8);u.reg_write(UC_X86_REG_RIP,target)
 def hook(u,address,size,_):
  rva=address-base
  if address==stop:u.emu_stop();return
  if 0x25080<=rva<0x25a64:
   if rva in (0x254cf,0x25567,0x2578d,0x259bb,0x259c4,0x25a23):visited.append(hex(rva))
   return
  calls.append(hex(rva))
  if rva==0x35ca30:ret();return
  if rva==0x58d9b0:
   # PCI-config helper's out pointer is caller stack argument #6.
   sp=u.reg_read(UC_X86_REG_RSP);out=struct.unpack('<Q',u.mem_read(sp+0x30,8))[0]
   w32(out,0);ret();return
  raise RuntimeError(f'unexpected outside instruction {rva:x}')
 u.hook_add(UC_HOOK_CODE,hook);u.emu_start(base+0x25080,stop+1,count=10000)
 assert u.reg_read(UC_X86_REG_RIP)==stop
 return dict(platform_internal=hex(platform),state_e98=state,vendor_e9c=3,vf_mode_45660=vf_mode,resource_count=2 if extra_resource else 1,status=hex(u.reg_read(UC_X86_REG_EAX)),flags_c98=hex(struct.unpack('<I',u.mem_read(obj+0xc98,4))[0]),flags_c9c=hex(struct.unpack('<I',u.mem_read(obj+0xc9c,4))[0]),visited=visited,stubbed_calls=calls)
results=[run(platform,state,extra) for platform in (0x4f8,0x4f9) for extra in (False,True) for state in (0,2)]
out=dict(binary=str(binary),sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),parser_rva='0x25080',method='original resource-parser bytes; synthetic resource descriptors; logging and PCI config reads stubbed; not actual guest trace',results=results)
(root/'windows/analysis/9033-resource-emulation.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
