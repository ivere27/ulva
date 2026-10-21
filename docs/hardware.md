# Hardware reference

Ulva v0.42 is a carrier for the **ESP32-C5-DevKitC-1 v1.2 with PSRAM**.
The PCB is 100 × 100 mm, two-layer FR-4, 1.6 mm thick, with 1 oz copper per
side. It has 106 footprints and eight schematic sheets. Peripheral modules
plug into the connections below. The reference schematic sheet contains
external interface notes and adds no carrier components.

## GPIO assignment

Viewed from the component side, J6 is the left DevKit socket and J7 the right.
Both have pin 1 at the top; USB connectors point down. The two 1 × 16 socket
rows are 22.86 mm apart. The C6 DevKit is not compatible with this pinout.

| GPIO | Socket | Function |
|---:|---|---|
| 0 | J6.5 | RTC interrupt, active LOW; 10 kΩ pull-up |
| 1 | J6.6 | Button ADC, ADC1_CH0 |
| 2 / 3 | J6.3 / J6.4 | I2C0 SDA / SCL, LP-I²C |
| 4 | J7.8 | Passive piezo PWM through R26 1 kΩ; idle LOW |
| 5 | J7.9 | 24 V input monitor, ADC1_CH4 |
| 6 | J6.7 | Configuration DIP ADC, ADC1_CH5 |
| 7 / 8 | J6.8 / J6.9 | CAN2 (CAN FD) TX / RX; TX has a 10 kΩ pull-up |
| 9 / 10 | J6.10 / J6.11 | I2C1 SDA / SCL, HP-I²C |
| 11 / 12 | J7.2 / J7.3 | DevKit UART0 TX / RX; carrier NC |
| 13 / 14 | J7.14 / J7.13 | DevKit USB D− / D+; carrier NC |
| 23 / 24 | J7.5 / J7.4 | CAN1 (CAN FD) RX / TX; TX has a 10 kΩ pull-up |
| 25 | J6.13 | ZONE_ENABLE; 10 kΩ pull-down, default LOW |
| 26 | J6.12 | RF433 RX through R11 1 kΩ |
| 27 | J7.7 | DevKit RGB LED; carrier NC |
| 28 | J7.11 | DevKit BOOT; carrier NC |

J6.1=3V3, J6.14=EXP_5V, J6.15=GND; J7.1/12/15=GND.
J6.2/16 and J7.6/10/16 are unconnected on the carrier. GPIO15/SPICS1 is
reserved for PSRAM, and GPIO16–22 are not external spare pins. No spare GPIO
remains. Preserve the DevKit boot configuration and existing pulls on strap
pins; set the GPIO25 output latch LOW before enabling its output.

## Connectors

Pin numbers refer to the PCB; the cable mating face is mirrored. Square pads
identify pin 1. Match the actual module pinout before insertion, particularly
RTC, RF433 and OLED modules, which are sold with different pin arrangements.

| Connector | Pin order / purpose |
|---|---|
| J1, DHT20 | 1=3V3, 2=SDA1, 3=GND, 4=SCL1 |
| J2, RTC | 1=3V3, 2=GND, 3=SDA0, 4=SCL0, 5=RTC_INT_N |
| J3, OLED | 1=GND, 2=3V3, 3=SCL0, 4=SDA0 |
| J4, RF433 | 1=ANT, 2=3V3, 3=DO, 4=GND |
| J5, passive piezo | 1=PWM through R26, 2/3=NC, 4=GND |
| J8 / J9 | AC0 / AC1: I2C0 / I2C1 |
| J10 / J11 | DC0 / DC1: I2C0 / I2C1 |
| J12–J17 | Six parallel AC2_IN terminals |
| J18–J23 | Six parallel DC_DRIVER_COM terminals; command return only |
| J24 / J25 | +24 V DC input / POWER_0V input |
| J26 / J27 | CAN1 / CAN2 (CAN FD): 1=fused +24 V, 2=POWER_0V, 3=H, 4=L |

J8/J10 mate from below, J9 from the left and J11 from the right. J12–J14
and J18–J20 are at the bottom; J15–J17 are on the left and J21–J23 on the
right. J26 mates from the right, J27 from the left. J24/J25 are at the upper
right. USB and lower IDC mating spaces overlap in plan view; clearance depends
on the fitted sockets, plugs and strain reliefs.

The four expansion headers use a 2 × 5, 2.54 mm layout:

| Pins | AC ports J8/J9 | DC ports J10/J11 |
|---|---|---|
| 1–2 | NC | NC |
| 3–4 | NC | DC_ZONE_RETURN |
| 5–6 | EACRET | NC |
| 7 / 8 | SDA / SCL for that bus | SDA / SCL for that bus |
| 9 / 10 | EXP_5V / logic GND | EXP_5V / logic GND |

## OpenSprinkler AC/DC expansion

J8–J11 are designed for compatibility with **OpenSprinkler AC/DC Expander 3.1**
interfaces, using PCA9555 I²C expanders and 2 × 5 IDC connectors. The upstream
[AC](https://github.com/OpenSprinkler/OpenSprinkler-Hardware/blob/master/Expander/3.0/AC/exp31ac.sch)
and [DC](https://github.com/OpenSprinkler/OpenSprinkler-Hardware/blob/master/Expander/3.0/DC/exp31dc.sch)
schematics are available in the official
[OpenSprinkler hardware GitHub repository](https://github.com/OpenSprinkler/OpenSprinkler-Hardware).

Each I²C bus supports up to four AC/DC expanders combined at unique addresses
0x24–0x27, eight boards total. AC and DC ribbon chains stay separate, with
all ten pins connected straight 1:1. Both AC return conductors, pins 5/6,
are required. I2C0 serves OLED/RTC/J8/J10; I2C1 serves DHT20/J9/J11.
Both buses use 4.7 kΩ pull-ups directly to 3V3 with 5 V expander power.
PCA9555 specifies `VIH(min) = 0.7 × VDD`; input-HIGH margin depends on the
actual expander supply.
I2C0/I2C1 are board names: GPIO2/3 use LP-I²C and GPIO9/10 use HP-I²C.

## Power and output enable

J24 supplies nominal 24 V DC to U2 SY8301ABC/L1 and the two CAN power fuses.
The buck target is 5.096 V before D4; EXP_5V is lower by D4's forward drop.
EXP_5V connects to DevKit J6.14, expansion pin 9, K1's coil and DC gate bias.
The DevKit supplies 3V3. U2 stays enabled when ZONE_ENABLE is LOW.

J25 POWER_0V connects directly to CAN pin 2 and through NT1 to logic GND.
NT1 does not connect DC_DRIVER_COM. D4 limits USB-to-buck reverse current;
USB coexistence also depends on the actual DevKit's VBUS blocking diodes.
The raw 24 V input has no input fuse, TVS or reverse-polarity protection.

| Circuit | Design budget |
|---|---|
| AC, J8 + J9 combined | ≤2 A RMS; one isolated 24 V AC source; harness/socket ambient ≤40°C |
| CAN control power, J26 + J27 combined | ≤1 A at nominal 24 V DC; ambient ≤40°C |
| DC_DRIVER_COM | Initial 0.5 A combined command-return budget |
| 5 V expansion loads | ≤210 mA combined, including K1 coil and DC gate bias |

These are design budgets, not qualified continuous ratings or hardware current
limits. Motor power uses separate wiring.

**AC:** source wire 1 connects to the external common of every AC load. Wire 2
passes through one external inline fuse into any J12–J17 terminal, then K1's
normally open contact and EACRET to expansion pins 5/6. All six input terminals
are parallel. Connecting wire 2 separately to EACRET, logic GND or PSU negative
would bypass the fuse/K1 path. The AC harness specification uses 26 AWG ribbon
and both return contacts.

**DC:** driver COM and J25 share the same external PSU negative reference but
remain separate PCB nets. U1 LTV-817S-TA1-C drives Q2 AO3400A between
DC_ZONE_RETURN and DC_DRIVER_COM. GPIO25 drives both this switch and K1;
if K1 is fitted, it energizes even for DC-only use. This is a shared-ground
circuit.
An external return path through LOW expander channels' 10 kΩ/390 Ω resistor
networks can remain when Q2 is OFF; actual driver release is unverified.
Initialize expander OFF data before configuring outputs and enabling GPIO25.

ZONE_ENABLE does not cut CAN power or provide a robot-wide hardware stop.
Motor protection and emergency stopping belong to the external equipment.
The carrier is not a protective-earth path.

## CAN FD

Each bus uses a 3V3 TPT1334-SO1R transceiver (supporting CAN FD data rates up to
5 Mbps), 100 nF + 1 µF decoupling, TX pull-up and PESD2CANFD24V protection on H/L.
SHDN/STB are tied LOW. The ESP32-C5 native TWAI controllers support ISO 11898-1:2015
CAN FD frames with up to 64-byte payloads as well as Classical CAN. The channels
share power/GND, are not isolated and require separate TWAI instances. CAN FD
firmware and a qualified bitrate are not supplied.

JP1/JP2 are normally closed copper jumpers enabling the respective 120 Ω
termination. Terminate each bus at its two ends only; cut its jumper when
Ulva is an intermediate node. Use a twisted H/L pair with short stubs.

The connectors are AMASS XT30PW(2+2)-M.G.B, mating with XT30(2+2)-F.G.B.
F2/F3 are 1.5 A fast fuses and do not block reverse feeding. Use one 24 V
source for both chains; disconnect the +24 V through-wire at a separately
powered node. Confirm cable polarity and H/L continuity at both ends.

## Analog inputs and assembly notes

Buttons, DIP and voltage monitoring use ADC1 oneshot with 12 dB attenuation,
calibrated readings and disabled internal pulls. Share one ADC1 handle.

SW2/SW3/SW4 are UP/OK/DOWN, using R12=10 kΩ, R13=4.7 kΩ, R14=10 kΩ and
C15=100 nF. The [button example](../firmware/buttons_adc/README.md) scans every
10 ms with 30 ms debounce.

| Button | Nominal voltage | Decoding interval |
|---|---:|---:|
| UP | 0 V | −50 to 250 mV |
| OK | 1.055 V | 800 to 1300 mV |
| DOWN | 1.964 V | 1650 to 2300 mV |
| None | 3.3 V | 2850 to 3600 mV, including upper saturation |

Gaps are INVALID. Simultaneous presses prioritize UP, then OK, then DOWN.
Shorts to GND/3V3 cannot be distinguished from valid states.

SW1 uses 1 kΩ pull-ups, 10 kΩ/20 kΩ weights and C12=100 nF. Its nominal
voltages are ON/ON=0 V, ON/OFF=1.065 V, OFF/ON=2.129 V and OFF/OFF=3.3 V.
SW1 sits in the central gap directly above the AC0/DC0 headers. With board
text upright, switch 1 is above switch 2; follow the body ON mark.
Both ON draw up to about 7 mA, including during sleep. Application functions
are not assigned by the example firmware.

The input monitor uses R31=150 kΩ, R32=10 kΩ, R33=1 kΩ and C16=100 nF:
`VIN_mV = ADC_mV × 16`, nominally 1.5 V at a 24 V input. D7 BAT54S has
1=logic GND, 3=ADC node and 2=3V3. Its clamp can backfeed 3V3 when 24 V
remains present with 3V3 off; it does not isolate the unpowered rail.

J5 takes a high-impedance passive piezo: red to pin 1, black to pin 4,
pins 2/3 empty. It has no supply pin. GPIO4 PWM is independent of GPIO27 RGB.

For D1 KT-0805G, align the cathode mark to PCB K: KiCad pad 1=K/pad 2=A,
while the KENTO drawing numbers 2=K/1=A. Follow polarity, not the vendor's
numeric pin 1. D7 pin assignments likewise depend on the specified BAT54S
variant. U2/L1 are required manual SMT parts; NT1/JP1/JP2 are PCB copper.
