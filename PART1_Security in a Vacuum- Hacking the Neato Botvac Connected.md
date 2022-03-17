# Security in a Vacuum: Hacking the Neato Botvac Connected, Part 1

**Note** this post was originally published on the NCC Group Blog at https://www.nccgroup.trust/us/about-us/newsroom-and-events/blog/2018/march/security-in-a-vacuum-hacking-the-neato-botvac-connected-part-1/ . However, it did not survive the NCC Group blog migration to a new platform, so I uploaded it here. It's also possible to view it on [archive.org](https://web.archive.org/web/20201221181915/https://www.nccgroup.com/us/about-us/newsroom-and-events/blog/2018/march/security-in-a-vacuum-hacking-the-neato-botvac-connected-part-1/). 


## Introduction

The Neato Botvac Connected is the first robot in the Neato line of robot vacuums that you can control using a smart phone. The idea of an Internet-connected robot capable of moving around your home intrigued (and frightened) me, so I decided to get one. This blog post is part one of a two-part series where I describe how I went about assessing this robot for security vulnerabilities, what I found, and how I exploited them.

I tested firmware version 2.2.0, which is the latest version as of this writing. My tests included only what was on the robot itself; I did not attempt to assess the cloud services on Neato’s backend. I focused on vulnerabilities that could be exploited by a network attacker without physical access to the robot.


## Overview of Setup API

The robot has an HTTPS-based API for setup on port 4443. The entire setup process normally works like this:

1. The robot creates a WiFi access point named “neato-[serial number]”.
2. You connect your phone to this access point and open the Neato app.
3. The app sends a GET request to the `/wifis` endpoint, which returns a JSON list of the wireless access points the robot can see.
4. The user chooses their WiFi SSID from the list and enters the password.
5. The app sends a PUT request to `/robot/initialize` with the user’s WiFi credentials and other setup options.
6. The robot turns off its wireless AP and connects to your WiFi network.

The main endpoint on the setup API is `/robot/initialize`, which receives the configuration data. A normal call to this endpoint from the app looks like:

```
PUT /robot/initialize
Host: 192.168.0.1:4443
Content-Type: application/json
Connection: keep-alive
Accept: */*
User-Agent: Botvac/407 CFNetwork/808.3 Darwin/16.3.0
Content-Length: 261
Accept-Language: en-us
Accept-Encoding: gzip, deflate

{"name":"Rosie", "ssid":"<your SSID>", "timezone":"America\/Chicago", "password":"<your WiFi password>", "server_urls":{"nucleo":"nucleo", "ntp":"pool.ntp.org", "beehive":"beehive"}, "user_id":"<your Neato user ID>", "utc_offset":"UTC-6:00UTC-5:00"}
```

Although the API only appears to be used during the setup phase, the service is never closed — once the robot is on your local network, the API is still accessible and you can send it new configurations at any time.

## Methodology

### Capturing Setup API Traffic

The Neato app assumes that wireless access points whose SSIDs are prefixed with the string “neato-“ are robot APs. When you connect your phone to such an AP and open the Neato app, it allows you to go through the setup process, issuing API requests to `192.168.0.1:4443`. I captured API traffic between the app and the API in the  following way:

1. I used a Raspberry Pi to create a network named “neato-asdfasdf”, with the Pi having an IP address of `192.168.0.1`.
2. I set up a web server on port 4443 on the Pi which dumps the raw HTTP requests to the terminal.
3. I connected my phone to the rogue AP and opened the Neato app. Then I went through the setup process, capturing its requests to the web server.
4. I connected my laptop to the actual Neato wireless AP and manually relayed the requests recorded above, capturing the responses.
5. I modified my rogue API server to send the same responses as the actual robot did.
6. I repeated until the entire setup process was complete.

Since the API has a small number of endpoints, I had sample requests/responses for all endpoints in about 15 minutes. For a more complicated API, it would be more efficient to automate this process by using a transparent proxy.

### Capturing Network Traffic

I configured the robot to connect to a Raspberry Pi WiFi access point which routed traffic to my normal network. This allowed me to see what network traffic the configured robot was generating via `tcpdump`.

## Vulnerability #1: Command Injection in ‘ntp’ Field 

NTP settings have proven to be a source of [command injection vulnerabilities](https://en.wikipedia.org/wiki/Code_injection#Shell_injection) in previous assessments I have performed (perhaps because invoking the `ntpdate` command is the easiest way to update the system time based on an NTP server). For this reason, the `ntp` field in the PUT request to `/robot/initialize` caught my interest. I sent the following JSON to the `/robot/initialize` endpoint:

```
{…, "server_urls":{"nucleo":"nucleo", "ntp":"`echo test`", "beehive":"beehive"}, …}
```

Through `tcpdump` on my Raspberry Pi I could see the robot making DNS requests for `test`, suggesting that the command had executed. I now had the ability to execute commands on the robot, but the process was painful for several reasons:

1. The only way to get output was by sniffing the DNS traffic on the Pi (requiring a man-in-the-middle position).
2. The data isn’t encoded for DNS transfer so a lot of it gets lost.
3. The robot doesn’t frequently update the date based on the NTP server, so the fastest way to test was to reboot the robot after each command.

In part two of this blog series, I will detail how I developed a command I/O channel to get around these limitations and obtain a pseudo shell on the robot.

## Vulnerability #2: Robot Hijacking

The `/robot/initialize` request takes a `user_id` parameter. This `user_id` is then associated with the robot on Neato’s cloud services, allowing them to control the robot via the Neato app. If a malicious user on the same network as the robot sends the following JSON in a PUT request to `/robot/initialize`:

```
{…, "user_id":"<evil user's Neato ID>", …}
```

they have now associated the robot with their own Neato account. This would allow the attacker to:

* Start/stop the robot at will.
* Manually drive the robot (but only if they are on the same local network as the robot).
* View maps the robot has generated.

This means that anyone on the same local network as a Neato Botvac Connected can hijack it.

## Vulnerability #3: Format String Vulnerability in ‘/wifis’ Endpoint

Making a GET request to `/wifis` returns a JSON list of all the WiFi networks that the robot can see. This is used during the setup process so that users can select a WiFi network to connect to. The response normally looks like:

```
{"wifi": [{"ssid":"FBI Surveillance Van"},{"ssid":"xfinitywifi"},…]}
```

If an attacker creates a wireless network with an SSID containing a C-style format string, such as “%x%x%x%x”, the endpoint responds with the following:

```
{"wifi":[…,{"ssid":"ffffe7f4"},…]}
```

This suggests that a string containing the SSID is being passed as a format string parameter somewhere during the construction of the response JSON. As the SSID is untrusted data, this results in a [format string vulnerability](https://en.wikipedia.org/wiki/Uncontrolled_format_string). 

Anyone able to create a wireless network in range of the robot during setup time is theoretically able to exploit this vulnerability. However, it has some limitations:

* WiFi SSIDs can only be a maximum of 32 characters. If the malicious payload needs to be larger than 32 characters, it is possible to create *multiple* wireless networks with format strings; they will all be executed as a single format string by the API. However, it’s still not possible to control a contiguous block of string greater than 32 characters long.
* The C library on the robot does not understand specifying offsets via the ’`$`’ character. 
* The attacker would be doing this blind — unless they own the robot, they won’t be seeing the results of the `/wifis` request.

Because of the limitations, I did not attempt to get code to execute via the vulnerability (though it may be possible to do so). However, it is easily possible to deny the Neato owner the ability to set up their robot by creating a nearby network with the name “`%n%lx`” — this string causes the robot’s web server to crash, requiring the robot to be rebooted.

## Unexplored Attack Surface

There are plenty of remaining topics I did not yet have time to investigate:

* The second web server which is used for driving the robot via WebSockets.
* The custom binaries on the device, like `/bin/robot`.
* The encrypted syslog files which you can dump to a USB drive using a menu on the robot — Where is the key? What sensitive info might be in these dumps?
* Using the command injection to physically control or damage the robot in some way.

## Wrapping Up

Although Neato has not issued a patch for the vulnerabilities listed above, none of them can be exploited from the Internet, so they are not as serious as they could be. If the robot is on a network with untrusted users, enabling host isolation or otherwise segmenting the robot from the hostile users could work well. Alternatively, performing a TCP connect scan of the robot with `nmap` causes the web server to crash. This effectively mitigates the issues until the next reboot, since it’s not possible to exploit them without the web server (though it’s clearly not the *best* solution…)

Stay tuned for part two of the series, where I will dive into the development of a command I/O channel using the command injection vulnerability.

### Vendor Communication

* **03/14/17** — Emailed Neato Robotics asking for security contact address and initial ticket started
* **03/23/17** — A follow-up was sent to the initial ticket
* **04/14/17** — A second ticket was opened
* **04/17/17** — NCC successfully reached out to Neato Robotics via Twitter
* **04/20/17** — Vulnerabilities disclosed to Neato Robotics engineering team
* **04/21/17** — Receipt of advisories acknowledged by Neato
* **07/31/17** — Follow up email requesting status update sent to Neato
* **01/09/18** — Notification of intent to publish sent to Neato


