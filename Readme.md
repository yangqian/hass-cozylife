# hass-cozylife

## What is it

This a third-party home assistant custom components works for Cozylife Lights based on [the official repository](https://github.com/cozylife/hass_cozylife_local_pull). The official repo is buggy in too many ways. This one heavily modified. 

* It is a pure local version and does not use UDP discovery.

* The color temperature is fixed.


## features

* heartbeat to each bulb in a fix time interval to test the availability. Even if the bulb is not available during the time of setup or later, it can pick it up if the bulb goes online again.
* async
* fixed the color temperature


## Tested Product 

Tested it on [color bulbs (no homekit)](https://detail.1688.com/offer/617699711703.html?spm=a2615.2177701.autotrace-offerGeneral.1.12be5799WNMB96).
It can be initialized though bluetooth. 

Switch and CW lights are not tested yet.
CW lights should work.

## How I Setup the bulb

The bulb will phone home to dohome.doiting.com. I blocked the dns request (you might also be able to block the internet access entirely, have not tested). This makes the registration process half complete. 
But the app could transmit the wifi name and password to the bulb. 
In principle, if you complete the full registration with the cloud, the bulb will respond to UDP discovery.
However, my bulbs does not respond to UDP discovery, not sure if is because the code I used was buggy.

Instead, we run a TCP scan on the operating port 5555 through a specific ip range.

Note that for we must have persistent IP address otherwise the config will change. Thus can be done on most routers.

### Sample config

Run
```
python3 getconfig.py
```
to obtain something like
```
light:
- platform: cozylife
  lights:
  - ip: 192.168.1.193
    did: 637929887cb94c4cffff
    pid: p93sfg
    dmn: Smart Bulb Light
    dpid: [1, 2, 3, 4, 5, 7, 8, 9, 13, 14]
  - ip: 192.168.1.194
    did: 637929887cb94c4ceeee
    pid: p93sfg
    dmn: Smart Bulb Light
    dpid: [1, 2, 3, 4, 5, 7, 8, 9, 13, 14]
```

Copy it to the relevant configuration file (yaml). Here the did is the same as of the official app (unique id). pid, dmn, dpid are also the same as the official app.

### Optional requirements

    [Circadian Lighting](https://github.com/claytonjn/hass-circadian_lighting)
    I used a modified v1 version (with Astral v2 dependance). v2 is not tested.

## Notes and todo

* Nothing is encrypted. If it talks to the cloud, I guess it also talks to the cloud unencrypted. In the file model.json, even the ota update file is not encrypted. If someone could crack it. One might be able to flash custom firmware via OTA.

* Implement effects, the formats are listed below

* The color is not accurate at all (to be fixed? I am not sensitive to colors).

### summary for control parameters:

* '1': on off switch
* '2': 0 normal change to color / color temperature with a transition period

* '2': 1 with special effects
* '4' brightness
* '5' hue
* '6' saturation
* '8' speed of change
* '7' consists of two bits of operator and 7 colors

* colors are in the format of HHHH SSSS TTTT
where HHHH SSSS are hue and saturation.
TTTT is color temperature.
* In color mode, TTTT=FFFF.
* In white mode, HHHH SSSS =FFFF FFFF.

### operator code for effects:

#### List (applicable to color or color temperature, or a mix of the two)


04: 1 on off rotation
05: 2 on off rotation
06: 3 on off rotation
07: 7 on off rotation

08: 1 slowly diming
09: 2 slowly diming
0a: 3 slowly diming
0b: 7 slowly diming

0c: 1 fast flash
0d: 2 fast flash
0e: 3 fast flash
0f: 7 fast flash

#### Only for color 

00: 1 smooth change color rotation 
01: 2 smooth change color rotation 
02: 3 smooth change color rotation
03: 7 smooth change color rotation (rainbow effects)

#### Note for color temperature

00: brief dim and increase back up '8' does not matter, 01 FFFF FFFF TTTT.
01: identical to mode '2':0, but it is a sudden change instead of a smooth transition.

#### Raw status obtained from the app

##### gorgeous (rainbow)

{'1': 1,
 '2': 1,
 '4': 1000,
 '7': '03 0000 03E8 FFFF 0078 03E8 FFFF 00F0 03E8 FFFF 003C 03E8 FFFF 00B4 03E8 FFFF 010E 03E8 FFFF 0026 03E8 FFFF',
 '8': 500}
 0078: 120
 00F0: 240
 003C: 60
 00B4: 180
 010E: 270
 0026: 38

##### Dazzling (3 color green blue red)

{'1': 1,
 '2': 1,
 '4': 1000,
 '7': '06 0000 03E8 FFFF 0078 03E8 FFFF 00F0 03E8 FFFF 000000000000000000000000000000000000000000000000',
 '8': 800}

##### Profusion (7 colors)

{'1': 1,gg
 '2': 1,
 '4': 1000,
 '7': '07000003E8FFFF007803E8FFFF00F003E8FFFF003C03E8FFFF00B403E8FFFF010E03E8FFFF002603E8FFFF',
 '8': 800}


##### Single color 

Soft (0078: 120  03E8: 1000)
{'1': 1,
 '2': 1,
 '4': 1000,
 '7': '08 0078 03E8 FFFF F000 00000000000000000000000000000000000000000000000000000000000000000000',
 '8': 500}

Casual: (brightness 500, color temp 500)

{'1': 1,
 '2': 1,
 '4': 500,
 '7': '01 FFFF FFFF 01F4 FFFF FFFF 01F4000000000000000000000000000000000000000000000000000000000000',
 '8': 1000}

Work: (brightness 1000, color temp 1000)

{'1': 1,
 '2': 1,
 '4': 1000,
 '7': '01 FFFF FFFF 03E8 FFFF FFFF 03E8 000000000000000000000000000000000000000000000000000000000000',
 '8': 1000}

Goodnight: (brightness 100, color temp 0)

{'1': 1,
 '2': 1,
 '4': 100,
 '7': '01 FFFF FFFF 0000 FFFF FFFF 0000 000000000000000000000000000000000000000000000000000000000000',
 '8': 1000}

Reading: (brightness 1000, color temp middle, 01F4: 500)

{'1': 1,
 '2': 1,
 '4': 1000,
 '7': '01 FFFF FFFF 01F4 FFFF FFFF 01F4 000000000000000000000000000000000000000000000000000000000000',
 '8': 1000}
