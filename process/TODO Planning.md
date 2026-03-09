## Material

- [ ] Raspberry Pi
- [ ] Headset (mic + speaker)
- [ ] Thermal/Printer
- [ ] 2 buttons
- [ ] RFID reader
- [ ] RFID tags

Random Access Memory
FAM - Family Access Memory
FLM - Family Language Model

## Monday

- [ ] Think 10 minutes project name (keep it in mind) #A-Z
- [ ] Concept discussion 10 minutes (telephone table, wood) #A-Z 
- [ ] Think how to include the thermal printer in the design, handset ? #A-Z 
(headset: look in interdiscount? tech shops?)

- [ ] Calculate dimensions of box + disks #Z
- [ ] Sketch what the phone could look like? #Z 
- [ ] 3D modeling of box + [inserts](https://webtechie.be/images/2022/3dprints/arcade-kit/box-design.png) for raspi + nfc, cables holes (3), buttons, easy opening #Z
- [ ] 3D modeling of disk #Z
- [ ] Setup Raspberry Pi (ssh + install python) + what wifi? #A
- [ ] Bootstrap code in repo #A
- [ ] Start box print #A-Z 
- [ ] Plan B for handset? Shops nearby #A-Z 

## Tuesday

Finalise scenario AI - Prompt #A (definition, adding, arguing, ask for spelling the word)
How does the AI pick a new word as a familect ? #A 
Connect buttons to raspberry Pi #A 
Soldering?? iron??
### Code
1. Implement STT LLM TTS AI #A -> is there a local alternative?
2. if button disk pressed allow the next step to happen:
	-> then activate RFID/NFC reader
	-> Button on top sends signal when not pressed (phone grab) -> start voice chat
	-> if one of two button change state -> stop whole interaction

GPIO => 2 [buttons](https://projects.raspberrypi.org/en/projects/rpi-gpio-wiring-a-button)
USB? => printer, handset?
### NFC code #Z 

Connect NFC reader to raspberry (test with SSH) #Z 
**Disk detection** (is it possible to store prompt on RFID tag?) see max char size #Z 
Else -> choose a number (1, 2, 3,) e.g. 1 = id for french #Z 

Connect printer to raspberry (test on laptop first?) #A 
Printer layout #A + validation #Z 

Test NFC with paper prototype to see where to put tag (front or back) #Z 
Print disks #A-Z 
NFC tags inside disks

## Wednesday

Finalise code, merge #A 
Install metallic structure (table phone) or 2 MDF bloc + coussin #A-Z ??
Virtual 3D Scenography of installation #Z 
(Ideally wood table with phone on the table and printer from the side)

## Thursday

!! Finalise documentation #A 
!! add images of user tests
!! create illustrated user journey
!! Add technical diagram + steps to reproduce + software #A 
!! Prepare presentation

Video Documentation (userjourney) #A-Z (also possible friday)

## Friday

Switch drive documentation
Github documentation
