# Bill of materials

The quantities below are for one **Ulva v0.42** carrier. The KiCad schematic
properties are the source of the part numbers; the PCB uses matching properties
and footprints. Plug-in modules, cables, mating connectors and mounting hardware
are additional items.

| Category | Quantity |
|---|---:|
| SMT parts tagged `JLC PCBA SMT` | 62 |
| Required manual SMT parts, U2 and L1 | 2 |
| Through-hole parts and antenna | 30 |
| PCB copper, holes, slots and test pad; no purchased component | 12 |
| **Total PCB footprints** | **106** |

There are **94 fitted parts** when fully populated. The tables record the design's
MPNs and LCSC numbers; they do not establish current stock, assembly availability
or library tier. A dash means that the corresponding sourcing field is not
recorded. See the [hardware reference](hardware.md) for wiring and power limits.

## SMT assembly candidates

These 62 parts carry the `JLC PCBA SMT` tag and are placed on the front side.
They form **26 part groups**, grouped by MPN, manufacturer, LCSC number and
footprint. The footprint column omits the KiCad library prefix.

| References | Qty | Value | Footprint | MPN | Manufacturer | LCSC |
|---|---:|---|---|---|---|---|
| C1, C5, C10, C12, C13, C15, C16 | 7 | 100nF; C5 explicitly marked 50V | `C_0603_1608Metric` | `CC0603KRX7R9BB104` | YAGEO | [C14663](https://www.lcsc.com/product-detail/C14663.html) |
| C3, C4, C8, C9 | 4 | 2.2uF / 50V | `C_1206_3216Metric` | `CL31B225KBHNNNE` | Samsung Electro-Mechanics | [C50254](https://www.lcsc.com/product-detail/C50254.html) |
| C6, C7 | 2 | 47uF / 10V | `C_1206_3216Metric` | `CL31A476MPHNNNE` | Samsung Electro-Mechanics | [C96123](https://www.lcsc.com/product-detail/C96123.html) |
| C11, C14 | 2 | 1uF | `C_0603_1608Metric` | `CL10A105KB8NNNC` | Samsung Electro-Mechanics | [C15849](https://www.lcsc.com/product-detail/C15849.html) |
| D1 | 1 | ZONE_ENABLE GREEN | `LED_0805_2012Metric` | `KT-0805G` | Hubei KENTO Elec | [C2297](https://www.lcsc.com/product-detail/C2297.html) |
| D2 | 1 | BZX84C8V2 | `SOT-23` | `BZX84C8V2` | hongjiacheng | [C22395522](https://www.lcsc.com/product-detail/C22395522.html) |
| D3 | 1 | 1N4148W | `D_SOD-123` | `1N4148W` | ST(Semtech) | [C81598](https://www.lcsc.com/product-detail/C81598.html) |
| D4 | 1 | SS34 | `D_SMA` | `SS34` | MDD | [C8678](https://www.lcsc.com/product-detail/C8678.html) |
| D5, D6 | 2 | PESD2CANFD24V-TR | `SOT-23` | `PESD2CANFD24V-TR` | Nexperia | [C552486](https://www.lcsc.com/product-detail/C552486.html) |
| D7 | 1 | BAT54S | `SOT-23` | `BAT54S` | hongjiacheng | [C7420333](https://www.lcsc.com/product-detail/C7420333.html) |
| F2, F3 | 2 | 1.5A fast | `Fuse_Littelfuse_467_0603` | `046701.5NRHF` | Littelfuse | [C187608](https://www.lcsc.com/product-detail/C187608.html) |
| Q1, Q2 | 2 | AO3400A | `SOT-23` | `AO3400A` | AOS | [C20917](https://www.lcsc.com/product-detail/C20917.html) |
| R1, R2, R3, R4, R13 | 5 | 4.7k | `R_0603_1608Metric` | `0603WAF4701T5E` | UNI-ROYAL | [C23162](https://www.lcsc.com/product-detail/C23162.html) |
| R5, R6, R11, R17, R26, R33 | 6 | 1k | `R_0603_1608Metric` | `0603WAF1001T5E` | UNI-ROYAL | [C21190](https://www.lcsc.com/product-detail/C21190.html) |
| R8, R12, R14, R15, R19, R23, R25, R27, R30, R32 | 10 | 10k | `R_0603_1608Metric` | `0603WAF1002T5E` | UNI-ROYAL | [C25804](https://www.lcsc.com/product-detail/C25804.html) |
| R16 | 1 | 2.2k | `R_0603_1608Metric` | `0603WAF2201T5E` | UNI-ROYAL | [C4190](https://www.lcsc.com/product-detail/C4190.html) |
| R18 | 1 | 330 | `R_0603_1608Metric` | `0603WAF3300T5E` | UNI-ROYAL | [C23138](https://www.lcsc.com/product-detail/C23138.html) |
| R20 | 1 | 47k | `R_0603_1608Metric` | `0603WAF4702T5E` | UNI-ROYAL | [C25819](https://www.lcsc.com/product-detail/C25819.html) |
| R21 | 1 | 51k | `R_0603_1608Metric` | `0603WAF5102T5E` | UNI-ROYAL | [C23196](https://www.lcsc.com/product-detail/C23196.html) |
| R22 | 1 | 2.7k | `R_0603_1608Metric` | `0603WAF2701T5E` | UNI-ROYAL | [C13167](https://www.lcsc.com/product-detail/C13167.html) |
| R24, R29 | 2 | 120 | `R_1206_3216Metric` | `1206W4F1200T5E` | UNI-ROYAL | [C17909](https://www.lcsc.com/product-detail/C17909.html) |
| R28 | 1 | 20k | `R_0603_1608Metric` | `0603WAF2002T5E` | UNI-ROYAL | [C4184](https://www.lcsc.com/product-detail/C4184.html) |
| R31 | 1 | 150k | `R_0603_1608Metric` | `0603WAF1503T5E` | UNI-ROYAL | [C22807](https://www.lcsc.com/product-detail/C22807.html) |
| SW2, SW3, SW4 | 3 | TS-1187A-B-A-B | `SW_XKB_TS-1187A_5.1x5.1mm` | `TS-1187A-B-A-B` | XKB Connection | [C318884](https://www.lcsc.com/product-detail/C318884.html) |
| U1 | 1 | LTV-817S-TA1-C | `SMDIP-4_W9.53mm` | `LTV-817S-TA1-C` | Lite-On | [C109227](https://www.lcsc.com/product-detail/C109227.html) |
| U3, U4 | 2 | TPT1334-SO1R | `SOIC-8_3.9x4.9mm_P1.27mm` | `TPT1334-SO1R` | 3PEAK | [C44859616](https://www.lcsc.com/product-detail/C44859616.html) |

## Manual assembly

U2 and L1 are required SMT parts tagged `Manual SMT`:

| References | Qty | Value | Footprint | MPN | Manufacturer | LCSC |
|---|---:|---|---|---|---|---|
| U2 | 1 | SY8301ABC | `SOT-23-6_Handsoldering` | `SY8301ABC` | Silergy | [C2927130](https://www.lcsc.com/product-detail/C2927130.html) |
| L1 | 1 | 4.7uH | `L_Sunlord_SWPA6045_6x6mm` | `SWPA6045S4R7MT` | Sunlord | [C78804](https://www.lcsc.com/product-detail/C78804.html) |

The following 30 parts use through-hole assembly. Only some carry an explicit
`Manual THT` tag; an empty assembly field does not make a part an SMT candidate.

| References | Qty | Use / value | Footprint | MPN | Manufacturer | LCSC |
|---|---:|---|---|---|---|---|
| J1, J3, J4 | 3 | DHT20, OLED and RF433 module sockets | `Samtec_SSW-104-01-G-S_1x04_P2.54mm` | `SSW-104-01-G-S` | — | — |
| J2 | 1 | DS3231 RTC socket | `Samtec_SSW-105-01-G-S_1x05_P2.54mm` | `SSW-105-01-G-S` | — | — |
| J5 | 1 | Passive piezo header; pins 1 and 4 used | `PinHeader_1x04_P2.54mm_Vertical` | — | — | — |
| J6, J7 | 2 | ESP32-C5-DevKitC-1 v1.2 sockets | `Samtec_SSW-116-01-G-S_1x16_P2.54mm` | `SSW-116-01-G-S` | — | — |
| J8, J9, J10, J11 | 4 | AC0, AC1, DC0 and DC1 expansion headers | `ZHOURI_DC3-2.54-10PAS_IDC_2x05_P2.54mm` | `DC3-2.54-10PAS` | — | [C2977596](https://www.lcsc.com/product-detail/C2977596.html) |
| J12, J13, J14, J15, J16, J17 | 6 | Six parallel AC2_IN terminals | `TerminalBlock_MetzConnect_360272_1x01_Horizontal_ScrewM2.6` | `360272` | — | — |
| J18, J19, J20, J21, J22, J23 | 6 | Six parallel DRIVER COM terminals | `TerminalBlock_MetzConnect_360272_1x01_Horizontal_ScrewM2.6` | `360272` | METZ CONNECT | — |
| J24, J25 | 2 | 24 V DC input positive / POWER_0V | `TerminalBlock_MetzConnect_360272_1x01_Horizontal_ScrewM2.6` | `360272` | METZ CONNECT | — |
| J26, J27 | 2 | CAN1 / CAN2 power and data | `AMASS_XT30PW_2plus2_M_Horizontal` | `XT30PW(2+2)-M.G.B` | AMASS | [C19268030](https://www.lcsc.com/product-detail/C19268030.html) |
| K1 | 1 | HF46F/5-HS1 relay | `Relay_SPST_Hongfa_HF46F_HS1` | `HF46F/5-HS1` | — | — |
| SW1 | 1 | 206-2ST configuration DIP switch | `SW_DIP_SPSTx02_Slide_9.78x7.26mm_W7.62mm_P2.54mm` | `206-2ST` | — | — |
| AE1 | 1 | 433 MHz wire / spring antenna | `TestPoint_THTPad_D2.0mm_Drill1.0mm` | — | — | — |

J1–J4 and J6/J7 specify Samtec SSW sockets; J12–J25 specify METZ CONNECT
360272 terminals; K1 specifies Hongfa HF46F/5-HS1 and SW1 specifies CTS 206-2ST.
Some manufacturer fields are empty in the source, as shown above. No alternate
LCSC part is approved by this table: matching pitch or a similar product name
alone does not establish footprint or electrical compatibility.

## Board features

These 12 footprints do not require purchased components:

| References | Qty | Feature | Footprint |
|---|---:|---|---|
| JP1, JP2 | 2 | Normally closed CAN termination copper bridges | `SolderJumper-2_P1.3mm_Bridged_Pad1.0x1.5mm` |
| NT1 | 1 | POWER_0V to GND copper bond | `NetTie-2_SMD_Pad2.0mm` |
| H1, H2, H3, H4 | 4 | M3 mounting holes | `MountingHole_3.2mm_M3` |
| H5, H6, H7, H8 | 4 | OLED mounting slots | `MountingSlot_4.0x2.7mm_M2_OLED` |
| TP2 | 1 | GND test pad | `TestPoint_Pad_D1.5mm` |

## Minimal bring-up guide: additional parts by stage

Start with the Basic/Preferred SMT parts fitted by your PCBA order, then add
only the functions you need after the USB controller stage. Quantities below
are per carrier; do not buy parts already fitted or on hand. Use the exact parts
in the BOM tables above.
Plug-in modules and cables are separate purchases, outside the carrier BOM.

| Stage | Additional carrier parts | External items / purpose |
|---|---|---|
| 1. USB-powered controller | J6, J7: two `SSW-116-01-G-S` sockets | ESP32-C5-DevKitC-1 **v1.2 with PSRAM**, with matching headers, and a USB data cable. Start with programming and the [button example](../firmware/buttons_adc/README.md); SW2/SW3/SW4 are SMT parts in the base order. |
| 2. Onboard 24 V supply | U2, L1, J24, J25: one each | Suitable 24 V DC supply and wiring. Adds the onboard 24 V-to-5 V supply for the controller and expansion circuits. Follow the [power limits and connections](hardware.md#power-and-output-enable). |
| 3. CAN FD interface, per channel | CAN1: U3, D5, J26; CAN2: U4, D6, J27; one of each for the chosen channel. Add the power-feed parts below when needed. | Mating `XT30(2+2)-F.G.B` connector, cable with twisted H/L pair, and a CAN FD peer. Follow the [termination and power wiring](hardware.md#can-fd). |
| 4. Optional local peripherals | Fit only the sockets, switch or antenna in the table below | Matching modules, as needed. These options do not require AC/DC expansion. |
| 5. Optional AC/DC expansion | Stage 2 and only the headers and terminals needed for the chosen ports; add K1 for AC operation | [OpenSprinkler AC/DC Expander 3.1 boards](https://github.com/OpenSprinkler/OpenSprinkler-Hardware/tree/master/Expander/3.0) and straight-through IDC cables, using Ulva's compatible interface. AC operation also needs an isolated 24 V AC source and external inline fuse. |

CAN data can run with the controller powered by USB. To supply 24 V node
power through the CAN connectors, also fit J24/J25 and F2 for CAN1 or F3 for
CAN2. U2/L1 are needed when powering the controller itself from 24 V.

For stage 4, choose peripherals independently:

| Function | Additional carrier parts | External item |
|---|---|---|
| DHT20 sensor | J1: one `SSW-104-01-G-S` | DHT20 module matching J1 |
| RTC | J2: one `SSW-105-01-G-S` | DS3231-compatible module matching all five J2 pins, including interrupt |
| OLED | J3: one `SSW-104-01-G-S` | 3.3 V-compatible I²C OLED module matching J3; mounting hardware if needed |
| RF433 receiver | J4: one `SSW-104-01-G-S`; AE1: one antenna | 3.3 V-compatible receiver matching J4; 433 MHz wire/spring antenna for AE1 |
| Passive piezo | J5: one 1 × 4 header | High-impedance passive piezo and lead, using pins 1 and 4 |
| Configuration switch | SW1: one CTS `206-2ST` | No module; application firmware assigns its meaning |

Match the [connector pin orders](hardware.md#connectors) before buying modules
and follow the [power budgets](hardware.md#power-and-output-enable) for expansion
loads. The repository provides a button firmware example; application support
for the other functions must be added separately.

For AC expansion, fit K1 (`HF46F/5-HS1`) to switch the AC return. DC-only
expansion uses U1/Q2 and does not require K1. Choose J8/J9 for AC0/AC1 or
J10/J11 for DC0/DC1
(`DC3-2.54-10PAS`, one per used port). Populate only the needed AC2_IN
terminals from J12–J17 and DRIVER COM terminals from J18–J23; terminals in
each group are parallel. Read the [OpenSprinkler expansion interface](hardware.md#opensprinkler-acdc-expansion)
and [AC/DC wiring and operating constraints](hardware.md#power-and-output-enable)
before connecting loads.

### Ordering additional parts later

1. Open or regenerate the [order selector](../tools/README.md) for the current
   board revision and set the number of carriers being upgraded.
2. Clear PCBA and Loose selections for parts already fitted, ordered or on
   hand. For a loose-parts-only order, clear all PCBA selections.
3. Select **Loose** only for the additional LCSC parts needed by your chosen
   stages. Download `lcsc-import.csv` and import it at LCSC; review quantities
   and pack sizes before ordering.
4. Source the remaining carrier parts by their exact MPNs in the tables above
   and `manual-parts.csv`. That CSV lists unresolved parts, so buy only the
   references you need. Order plug-in modules, mating connectors, cables and
   mounting hardware separately.

Save `selection.json` with each order. It records choices; the tool does not
track deliveries or automatically subtract previous purchases.

## Assembly and purchasing notes

- Use the [order preparation tool](../tools/README.md) to review the PCBA and
  loose-parts lists. For Basic/Preferred assembly, select only eligible SMT parts whose
  current JLCPCB listing confirms that tier. The stored `JLCPCB_Library` field is
  sourcing metadata, not a live quote. Buy omitted parts separately for manual
  assembly where their function is needed; keep the final BOM and placement file
  reference sets identical.
- U2 SY8301ABC has a [1 A device rating](https://www.silergy.com/download/downloadFile?ftype=note&id=3828&type=product).
  Its output target is 5.096 V before D4;
  EXP_5V depends on the diode drop and load. Follow the board's separate load
  budgets rather than treating the regulator rating as available expansion power.
- U1 drives Q2 in a shared-ground circuit. Its presence does not provide galvanic
  isolation of the DC interface. F2/F3 fuse the CAN positive feeds; they do not
  provide reverse-polarity or reverse-current blocking, guarantee fault selectivity,
  or enforce the combined 1 A CAN design budget.
- Check D1 cathode orientation and the specified D7 pinout as described in the
  [assembly notes](hardware.md#analog-inputs-and-assembly-notes). Match the actual
  module pin order before fitting the DevKit, RTC, OLED, DHT20 or RF433 module.
  The sockets listed here do not include those modules.
- Shipping, feeder charges and stock depend on the supplier's current checkout.
  LCSC/JLCPCB order consolidation has [specific conditions and recalculated
  shipping](https://www.lcsc.com/help-center/ordering-quotation/combine-lcsc-jlcpcb-orders).
