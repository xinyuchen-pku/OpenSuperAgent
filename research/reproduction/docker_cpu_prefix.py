"""Place an owned benchmark container on its frozen Docker-host CPU index."""
import os,sys
cpu,client,endpoint,*args=sys.argv[1:]
assert cpu.isdecimal()and int(cpu)>=0 and client.startswith('/')
assert endpoint.startswith(('unix://','tcp://'))and args
if args[0]=='run':args=['run','--cpuset-cpus',cpu,*args[1:]]
os.execv(client,[client,'--host',endpoint,*args])
