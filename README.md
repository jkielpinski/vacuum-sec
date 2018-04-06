# Neato Botvac Connected command injection pseudo shell

These scripts are a companion to my blog posts [Security in a Vacuum: Hacking the Neato Botvac Connected, Part 1](https://www.nccgroup.trust/us/about-us/newsroom-and-events/blog/2018/march/security-in-a-vacuum-hacking-the-neato-botvac-connected-part-1/) and [Security in a Vacuum: Hacking the Neato Botvac Connected, Part 2](https://www.nccgroup.trust/us/about-us/newsroom-and-events/blog/2018/april/security-in-a-vacuum-hacking-the-neato-botvac-connected-part-2/). They can be used to create a pseudo interactive shell on the robot.

## Usage

1. Run `exploit.sh` to establish blind command execution via POST bodies to the setup API server using a command injection vulnerability. Note that after running `exploit.sh`, you will no longer be able to control the robot from the mobile app until you set the robot up again in the normal way.
2. Either reboot the robot or wait for it to update its time from the NTP server.
3. Use `shell.py` to start a pseudo interactive shell. This:

   * Starts a rogue DNS server
   * Uses the blind command execution to update the robot's `resolv.conf` file to set the robot's DNS server to the attacker machine. 
   * Uploads a `encode.ksh` which encodes text for DNS exfiltration.
   * Handles sending commands via POST and receiving/decoding output via DNS.

Note that `shell.py` must be run as root so that it can bind to port 53 to create the DNS server.

## Known issues

`shell.py` is a bit glitchy sometimes. If the command output doesn't appear, or appears after you enter the next command. Just restart the script.