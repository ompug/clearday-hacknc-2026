#!/usr/bin/env python3
"""Rebuild the KiCad 8 schematic and placement study using standard libraries.

Run with Python from the pinned KiCad 8.0.9 container; see README.md.
All generated output stays beside this script. UUIDs are deterministic.
"""
import copy
import csv
import json
import math
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB = Path('/usr/share/kicad/symbols')
FP = Path('/usr/share/kicad/footprints')

def uid(s):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'clearday-home/rev-a/' + s))

def q(s):
    return json.dumps(str(s), ensure_ascii=False)

def parse(text):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[^\s()]+|[()]', text)
    stack, result = [], []
    for t in tokens:
        if t == '(':
            n = []
            (stack[-1] if stack else result).append(n)
            stack.append(n)
        elif t == ')':
            stack.pop()
        else:
            stack[-1].append(json.loads(t) if t.startswith('"') else t)
    return result[0]

def nodes(n, tag):
    return [c for c in n if isinstance(c, list) and c and c[0] == tag]

def one(n, tag):
    return next(c for c in nodes(n, tag))

def emit(n):
    if isinstance(n, list):
        quoted = {'property': {1,2}, 'symbol': {1}, 'name': {1}, 'number': {1}, 'text': {1}}
        return '(' + ' '.join(q(c) if i in quoted.get(n[0],set()) else emit(c) for i,c in enumerate(n)) + ')'
    if re.fullmatch(r'[a-zA-Z_~][a-zA-Z_0-9.-]*|[-+]?\d+(?:\.\d+)?', str(n)):
        return str(n)
    return q(n)

CACHE = {}
def symbol(libid):
    if libid in CACHE:
        return copy.deepcopy(CACHE[libid])
    lib, name = libid.split(':')
    tree = parse((LIB / (lib + '.kicad_sym')).read_text())
    raw = copy.deepcopy(next(n for n in nodes(tree, 'symbol') if n[1] == name))
    ext = nodes(raw, 'extends')
    if ext:
        base = symbol(lib + ':' + ext[0][1])
        old = base[1]
        base[1] = name
        for n in nodes(base, 'symbol'):
            n[1] = n[1].replace(old + '_', name + '_', 1)
        for p in nodes(raw, 'property'):
            base[:] = [n for n in base if not (isinstance(n, list) and n[:2] == p[:2])]
            base.append(p)
        raw = base
    CACHE[libid] = raw
    return copy.deepcopy(raw)

def pins(sym):
    return [p for sub in nodes(sym, 'symbol') for p in nodes(sub, 'pin')]

def prop(sym, key):
    return next((p[2] for p in nodes(sym, 'property') if p[1] == key), '')

LIBIDS = ['Connector:USB_C_Receptacle_USB2.0_16P', 'RF_Module:ESP32-S3-WROOM-1',
          'Regulator_Linear:AP7361C-33E', 'Power_Protection:USBLC6-2SC6',
          '74xGxx:74AHCT1G125', 'Audio:MAX98357A', 'Sensor_Audio:ICS-43434',
          'LED:WS2812B', 'Device:R', 'Device:C', 'Device:C_Polarized',
          'Device:LED', 'Device:Polyfuse', 'Switch:SW_Push',
          'Connector_Generic:Conn_01x02', 'Connector_Generic:Conn_01x04',
          'Connector_Generic:Conn_02x05_Odd_Even', 'power:PWR_FLAG']

if '--inspect' in sys.argv:
    for lid in LIBIDS:
        s = symbol(lid)
        print(lid, prop(s, 'Footprint'))
        print([(one(p, 'number')[1], one(p, 'name')[1], one(p, 'at')[1:], p[1]) for p in pins(s)])
    sys.exit()

CUSTOM = parse('''(symbol "TPS22918DBVR" (in_bom yes) (on_board yes)
 (property "Reference" "U" (at 0 12.7 0) (effects (font (size 1.27 1.27))))
 (property "Value" "TPS22918DBVR" (at 0 10.16 0) (effects (font (size 1.27 1.27))))
 (property "Footprint" "Package_TO_SOT_SMD:SOT-23-6" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
 (property "Datasheet" "https://www.ti.com/lit/ds/symlink/tps22918.pdf" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
 (symbol "TPS22918DBVR_0_1" (rectangle (start -7.62 7.62) (end 7.62 -7.62) (stroke (width 0.254) (type default)) (fill (type background))))
 (symbol "TPS22918DBVR_1_1"
 (pin power_in line (at -10.16 5.08 0) (length 2.54) (name "VIN" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
 (pin power_in line (at 0 -10.16 90) (length 2.54) (name "GND" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))
 (pin input line (at -10.16 0 0) (length 2.54) (name "ON" (effects (font (size 1.27 1.27)))) (number "3" (effects (font (size 1.27 1.27)))))
 (pin passive line (at -10.16 -5.08 0) (length 2.54) (name "CT" (effects (font (size 1.27 1.27)))) (number "4" (effects (font (size 1.27 1.27)))))
 (pin passive line (at 10.16 -5.08 180) (length 2.54) (name "QOD" (effects (font (size 1.27 1.27)))) (number "5" (effects (font (size 1.27 1.27)))))
 (pin power_out line (at 10.16 5.08 180) (length 2.54) (name "VOUT" (effects (font (size 1.27 1.27)))) (number "6" (effects (font (size 1.27 1.27)))))
 ))''')
CACHE['Clearday:TPS22918DBVR'] = CUSTOM
# KiCad 8 marks the MAX98357A thermal pad as unspecified. The datasheet
# requires GND, so retain the standard geometry in a local corrected symbol.
AMP_SYMBOL = symbol('Audio:MAX98357A')
for pin in pins(AMP_SYMBOL):
    if one(pin,'number')[1] == '17':
        pin[1] = 'power_in'
CACHE['Clearday:MAX98357A'] = AMP_SYMBOL

COMPONENTS = []
SHEETS = {}
ROOT_UUID = uid('power')
def sheet(key, title, number):
    SHEETS[key] = dict(title=title, number=number, uuid=uid(key), items=[], libs={})

for i, (key, title) in enumerate([('power', 'Power & USB'), ('mcu', 'MCU'),
                                 ('leds', 'LEDs'), ('audio', 'Audio'),
                                 ('inputs', 'Inputs & Expansion')], 1):
    sheet(key, title, i)

def text(sh, x, y, value, size=1.5):
    SHEETS[sh]['items'].append(f'(text {q(value)} (at {x} {y} 0) (effects (font (size {size} {size})) (justify left top)) (uuid {uid(sh+value)}))')

def add(sh, ref, lid, value, x, y, nets, mpn='', footprint='', manufacturer='', note=''):
    s = symbol(lid)
    SHEETS[sh]['libs'][lid] = s
    footprint = footprint or prop(s, 'Footprint')
    pp = pins(s)
    # Work on the standard 50-mil electrical grid.
    x, y = round(x/1.27)*1.27, round(y/1.27)*1.27
    top = min(-float(one(p, 'at')[2]) for p in pp)
    for sub in nodes(s,'symbol'):
        for rect in nodes(sub,'rectangle'):
            top=min(top,-float(one(rect,'start')[2]),-float(one(rect,'end')[2]))
    ident = uid(ref)
    path = '/' + ROOT_UUID + (('/' + uid('sheet-'+sh)) if sh != 'power' else '')
    flag = lid == 'power:PWR_FLAG'
    body = [f'(symbol (lib_id {q(lid)}) (at {x} {y} 0) (unit 1) (in_bom {"no" if flag else "yes"}) (on_board {"no" if flag else "yes"}) (dnp no) (uuid {ident})']
    for key, val, py, hide in [('Reference', ref, y+top-7.62, flag), ('Value', value, y+top-5.08, flag),
                              ('Footprint', footprint, y, True), ('Datasheet', prop(s,'Datasheet'), y, True),
                              ('MPN', mpn, y, True), ('Manufacturer', manufacturer, y, True), ('Notes', note, y, True)]:
        body.append(f'(property {q(key)} {q(val)} (at {x+6.35 if len(pp)==2 else x+12.7} {py} 0) (effects (font (size 1.27 1.27)) {"hide" if hide else ""}))')
    for p in pp:
        num = one(p, 'number')[1]
        body.append(f'(pin {q(num)} (uuid {uid(ref+"/"+num)}))')
    body.append(f'(instances (project "clearday-home" (path {q(path)} (reference {q(ref)}) (unit 1)))))')
    SHEETS[sh]['items'].append('\n'.join(body))
    seen = set()
    for p in pp:
        num = one(p, 'number')[1]
        px, py, angle = map(float, one(p, 'at')[1:])
        px, py = round(x+px, 4), round(y-py, 4)
        net = nets.get(num)
        if (px, py) in seen:
            continue
        seen.add((px, py))
        if net is None:
            if p[1] != 'no_connect':
                SHEETS[sh]['items'].append(f'(no_connect (at {px} {py}) (uuid {uid(ref+num+"nc")}))')
            continue
        dx, dy = {0:(-5.08,0), 90:(0,5.08), 180:(5.08,0), 270:(0,-5.08)}[int(angle)]
        ex, ey = round(px+dx,4), round(py+dy,4)
        SHEETS[sh]['items'].append(f'(wire (pts (xy {px} {py}) (xy {ex} {ey})) (stroke (width 0) (type default)) (uuid {uid(ref+num+"w")}))')
        # Global net labels connect the five sheets. Orient away from each pin.
        a = 180 if dx < 0 else 0 if dx > 0 else 90 if dy < 0 else 270
        SHEETS[sh]['items'].append(f'(global_label {q(net)} (shape bidirectional) (at {ex} {ey} {a}) (effects (font (size 1 1)) (justify {"right" if a in (180,270) else "left"})) (uuid {uid(ref+num+"label")}) (property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {ex} {ey} {a}) (effects (font (size 1 1)) hide)))')
    if not flag:
        COMPONENTS.append(dict(ref=ref, lib_id=lid, value=value, footprint=footprint, mpn=mpn,
                               manufacturer=manufacturer, notes=note, sheet=sh, nets=nets, uuid=ident, path=path))

RFP = 'Resistor_SMD:R_0603_1608Metric'
CFP = 'Capacitor_SMD:C_0603_1608Metric'
def r(sh, num, value, x, y, a, b, mpn=None):
    codes = {'0':'0R', '22':'22R', '100':'100R', '330':'330R', '1k':'1K', '4.7k':'4K7',
             '5.1k':'5K1', '10k':'10K', '100k':'100K', '560k':'560K'}
    add(sh, f'R{num}', 'Device:R', value, x,y, {'1':a,'2':b}, mpn or ('RC0603FR-07'+codes[value]+'L'), RFP, 'Yageo', '1%, 0.1 W')

def c(sh, num, value, x,y, net, ground='GND'):
    parts = {'100n':('GRM188R71C104KA01D', CFP, '16 V X7R'),
             '10n':('GRM188R71H103KA01D', CFP, '50 V X7R'),
             '1u':('GRM188R61A105KA61D', CFP, '10 V X5R'),
             '10u':('GRM21BR61A106KE19L','Capacitor_SMD:C_0805_2012Metric','10 V X5R'),
             '1000u':('EEU-FR1A102','Capacitor_THT:CP_Radial_D10.0mm_P5.00mm','10 V, D10 x H16 mm')}
    mpn, fp, note = parts[value]
    add(sh,f'C{num}','Device:C_Polarized' if value=='1000u' else 'Device:C',value,x,y,{'1':net,'2':ground},mpn,fp,'Panasonic' if value=='1000u' else 'Murata',note)

def flag(num, net, x,y):
    add('power', f'#FLG0{num:02}', 'power:PWR_FLAG','PWR_FLAG',x,y,{'1':net})

def build():
    text('power',20,15,'POWER & USB  |  5 V USB-C sink, native USB programming',2.2)
    add('power','J1','Connector:USB_C_Receptacle_USB2.0_16P','USB-C / USB 2.0',55,65,
        {**{p:'GND' for p in ['A1','A12','B1','B12','S1']}, **{p:'VBUS' for p in ['A4','A9','B4','B9']},
         'A5':'CC1','B5':'CC2','A6':'USB_DP_CONN','B6':'USB_DP_CONN','A7':'USB_DN_CONN','B7':'USB_DN_CONN'},
        'USB4105-GF-A','Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal','GCT')
    r('power',1,'5.1k',110,60,'CC1','GND')
    r('power',2,'5.1k',145,60,'CC2','GND')
    add('power','U2','Power_Protection:USBLC6-2SC6','USBLC6-2SC6',220,65,
        {'1':'USB_DP_CONN','6':'USB_DP_ESD','3':'USB_DN_CONN','4':'USB_DN_ESD','2':'GND','5':'VBUS'},'USBLC6-2SC6','','STMicroelectronics')
    c('power',1,'100n',270,65,'VBUS')
    r('power',3,'22',315,50,'USB_DP_ESD','USB_DP')
    r('power',4,'22',355,50,'USB_DN_ESD','USB_DN')
    text('power',290,85,'22 ohm resistors near MCU.\nRoute D+/D- as a 90 ohm differential pair.\nESD at connector; shell bonded to GND.')
    add('power','F1','Device:Polyfuse','2 A hold / 6 V',55,135,{'1':'VBUS','2':'+5V'},
        '1206L200/6','Fuse:Fuse_1206_3216Metric','Littelfuse','PTC; derate hold current with temperature')
    c('power',2,'1u',95,135,'+5V')
    add('power','U3','Regulator_Linear:AP7361C-33E','AP7361C-33E / 1 A',160,135,
        {'1':'+5V','2':'GND','3':'+3V3'},'AP7361C-33E-13','','Diodes Incorporated','SOT-223 tab is GND; thermal copper required')
    c('power',3,'10u',210,135,'+3V3')
    r('power',5,'1k',255,135,'+3V3','PWR_LED_A')
    add('power','D1','Device:LED','POWER green',305,135,{'1':'GND','2':'PWR_LED_A'},
        'LTST-C190KGKT','LED_SMD:LED_0603_1608Metric','Lite-On')
    flag(1,'VBUS',45,190)
    flag(2,'+5V',85,190)
    flag(3,'GND',125,190)
    text('power',20,215,'POWER POLICY\nUse a regulated 5 V / 3 A USB-C source for full output. No USB PD.\nFirmware must inspect CC1/CC2 and USB configuration before raising load.\nDefault current mode: LEDs and amplifier off; restrict radio activity.\nLDO dissipation: 0.51 W at 300 mA; verify temperature in the enclosure.\nLarge LED capacitor is isolated by U6 until firmware enables soft start.')
    r('power',6,'10k',250,190,'CC1','CC1_SENSE')
    c('power',4,'10n',295,190,'CC1_SENSE')
    r('power',7,'10k',340,190,'CC2','CC2_SENSE')
    c('power',5,'10n',385,190,'CC2_SENSE')
    for idx,key in enumerate(['mcu','leds','audio','inputs']):
        x,y=235+(idx%2)*80,212+(idx//2)*23
        SHEETS['power']['items'].append(f'''(sheet (at {x} {y}) (size 65 15) (stroke (width 0.254) (type default))
          (fill (color 0 0 0 0)) (uuid {uid('sheet-'+key)})
          (property "Sheetname" {q(SHEETS[key]['title'])} (at {x} {y-1.27} 0) (effects (font (size 1.27 1.27)) (justify left bottom)))
          (property "Sheetfile" "{key}.kicad_sch" (at {x} {y+16.27} 0) (effects (font (size 1.27 1.27)) (justify left top)))
          (instances (project "clearday-home" (path "/{ROOT_UUID}" (page "{idx+2}")))))''')

    text('mcu',20,15,'MCU  |  ESP32-S3-WROOM-1-N8R8',2.2)
    mcu = {'1':'GND','40':'GND','41':'GND','2':'+3V3','3':'EN','27':'BOOT',
           '13':'USB_DN','14':'USB_DP','4':'LED_DATA','5':'BTN_ACK','12':'I2C_SDA','17':'I2C_SCL',
           '18':'I2S_BCLK','19':'I2S_LRCLK','20':'I2S_DOUT','21':'I2S_DIN','22':'AMP_ENABLE',
           '9':'LED_ENABLE','37':'UART_TX','36':'UART_RX','39':'CC1_SENSE','38':'CC2_SENSE'}
    add('mcu','U1','RF_Module:ESP32-S3-WROOM-1','ESP32-S3-WROOM-1-N8R8',90,100,mcu,
        'ESP32-S3-WROOM-1-N8R8','','Espressif Systems','8 MB flash, 8 MB octal PSRAM; IO35/36/37 reserved')
    c('mcu',6,'10u',155,75,'+3V3')
    c('mcu',7,'100n',185,75,'+3V3')
    r('mcu',8,'10k',255,65,'+3V3','EN')
    c('mcu',8,'1u',295,65,'EN')
    add('mcu','SW1','Switch:SW_Push','RESET',345,65,{'1':'EN','2':'GND'},
        'B3U-1000P','Button_Switch_SMD:SW_SPST_B3U-1000P','Omron')
    r('mcu',9,'10k',255,125,'+3V3','BOOT')
    add('mcu','SW2','Switch:SW_Push','BOOT',315,125,{'1':'BOOT','2':'GND'},
        'B3U-1000P','Button_Switch_SMD:SW_SPST_B3U-1000P','Omron')
    text('mcu',230,155,'Hold BOOT, tap RESET, release BOOT to enter ROM loader.\nEN: 10k / 1u RC, approximately 10 ms.\nAll module GND pads, including exposed pad, connect to GND.')
    text('mcu',20,175,'GPIO ASSIGNMENTS\nGPIO1 / GPIO2     CC1_SENSE / CC2_SENSE (ADC1)\nGPIO4                 LED_DATA -> U5 level shifter\nGPIO5                 BTN_ACK, active low\nGPIO8 / GPIO9     I2C_SDA / I2C_SCL\nGPIO10 / GPIO11 I2S_BCLK / I2S_LRCLK, MCU master\nGPIO12 / GPIO13 I2S_DOUT to amp / I2S_DIN from mic\nGPIO14               AMP_ENABLE (high selects stereo mix)\nGPIO16               LED_ENABLE (slow-start switch)\nGPIO19 / GPIO20 USB_DN / USB_DP, native USB\nGPIO43 / GPIO44 UART_TX / UART_RX, 3.3 V logic',1.65)
    text('mcu',230,200,'RESERVED PINS\nGPIO0: BOOT only; external pull-up.\nGPIO3, GPIO45, GPIO46: strapping pins, no loads.\nGPIO35, GPIO36, GPIO37: octal PSRAM, no connection.\nDo not place copper or components in antenna keepout.\nUse a 15 mm clearance beyond the antenna where possible.\nKeep LED data and AMP_ENABLE low during startup.',1.65)

    text('leds',20,15,'LEDs  |  12-pixel RGB ring, switched 5 V',2.2)
    add('leds','U6','Clearday:TPS22918DBVR','TPS22918DBVR',60,55,
        {'1':'+5V','2':'GND','3':'LED_ENABLE','4':'LED_CT','6':'+5V_LED'},
        'TPS22918DBVR','','Texas Instruments','QOD intentionally open for 1000 uF load')
    c('leds',9,'1u',110,55,'+5V')
    c('leds',10,'10n',150,55,'LED_CT')
    r('leds',10,'100k',195,55,'LED_ENABLE','GND')
    c('leds',11,'1000u',240,55,'+5V_LED')
    text('leds',275,35,'CT = 10 nF: about 26 ms rise at 5 V.\n1000 uF charging current: about 0.2 A.\nQOD open; no forced capacitor discharge.\nAllow >= 50 ms before transmitting LED data.\nKeep LED_DATA low when U6 is off.')
    add('leds','U5','74xGxx:74AHCT1G125','74AHCT1G125',75,110,
        {'1':'GND','2':'LED_DATA','3':'GND','4':'LED_DATA_5V','5':'+5V_LED'},
        'SN74AHCT1G125DBVR','Package_TO_SOT_SMD:SOT-23-5','Texas Instruments')
    c('leds',12,'100n',135,110,'+5V_LED')
    r('leds',11,'330',185,110,'LED_DATA_5V','LED_DIN')
    r('leds',12,'100k',230,110,'LED_DATA','GND')
    for i in range(12):
        x=35+(i%6)*64
        y=168+(i//6)*66
        add('leds',f'D{i+2}','LED:WS2812B','WS2812B-V5',x,y,
            {'1':'+5V_LED','3':'GND','4':'LED_DIN' if i==0 else f'PIXEL_{i}',
            **({'2':f'PIXEL_{i+1}'} if i<11 else {})}, 'WS2812B-V5/W','','Worldsemi')
        c('leds',13+i,'100n',x+29,y,'+5V_LED')
    text('leds',20,268,'D2 -> D13 clockwise on PCB. Last DOUT is intentionally unused. One 100 nF capacitor per pixel.',1.4)

    text('audio',20,15,'AUDIO  |  Full-duplex I2S; mono speaker, left-channel microphone',2.2)
    add('audio','U4','Clearday:MAX98357A','MAX98357AETE+T',100,75,
        {'1':'I2S_DOUT','16':'I2S_BCLK','14':'I2S_LRCLK','4':'AMP_SD_MODE','2':'AMP_GAIN',
         '3':'GND','11':'GND','15':'GND','17':'GND','7':'+5V','8':'+5V','9':'SPK_P','10':'SPK_N'},
        'MAX98357AETE+T','','Analog Devices','Exposed pad to GND; BTL outputs, neither speaker wire is ground')
    c('audio',25,'100n',165,55,'+5V')
    c('audio',26,'10u',205,55,'+5V')
    r('audio',13,'560k',55,130,'AMP_ENABLE','AMP_SD_MODE')
    r('audio',14,'100k',115,130,'AMP_ENABLE','GND')
    r('audio',15,'100k',175,130,'+5V','AMP_GAIN')
    add('audio','J2','Connector_Generic:Conn_01x02','SPEAKER 4-8 ohm',285,70,
        {'1':'SPK_P','2':'SPK_N'},'B2B-PH-K-S(LF)(SN)',
        'Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical','JST','Use approximately 3 W speaker; floating BTL connection')
    text('audio',240,110,'SD_MODE: 560k from 3.3 V GPIO into internal 100k.\nNominal 0.500 V selects (L + R) / 2.\nGPIO low mutes. External 100k holds enable low at reset.\nGAIN_SLOT: 100k to VDD selects +3 dB.\nNever connect either speaker terminal to ground.\nNo headphone or grounded line-output connection.')
    add('audio','MK1','Sensor_Audio:ICS-43434','ICS-43434',100,210,
        {'1':'I2S_LRCLK','2':'GND','3':'GND','4':'I2S_BCLK','5':'+3V3','6':'I2S_DIN'},
        'ICS-43434','','TDK InvenSense','Bottom port: footprint acoustic hole must remain open')
    c('audio',27,'100n',170,210,'+3V3')
    r('audio',16,'100k',220,210,'I2S_DIN','GND')
    text('audio',260,190,'MCU supplies BCLK and LRCLK to both devices.\n48 kHz stereo frames, 32 bits per slot: 3.072 MHz BCLK.\nMicrophone outputs 24-bit data in left slot (LR = GND).\n100k SD pulldown defines the unused high-Z slot.\nNo MCLK needed. Decouple directly at each IC.\nDo not obstruct the microphone acoustic port.')

    text('inputs',20,15,'INPUTS & EXPANSION  |  Acknowledge button, I2C and UART',2.2)
    add('inputs','SW3','Switch:SW_Push','ACK / 12 mm',65,65,{'1':'BTN_RAW','2':'GND'},
        'B3F-4050','Button_Switch_THT:SW_PUSH-12mm','Omron','Rear-facing 12 mm tactile switch')
    add('inputs','J3','Connector_Generic:Conn_01x02','EXTERNAL BUTTON',65,115,
        {'1':'BTN_RAW','2':'GND'},'B2B-PH-K-S(LF)(SN)',
        'Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical','JST','Optional passive arcade switch; no external voltage')
    r('inputs',17,'1k',140,65,'BTN_RAW','BTN_ACK')
    r('inputs',18,'10k',200,65,'+3V3','BTN_ACK')
    c('inputs',28,'1u',255,65,'BTN_ACK')
    text('inputs',140,105,'Active low. 1k limits capacitor discharge current.\nPress time constant: 0.9 ms; low settles near 0.3 V.\nRelease time constant: 10 ms. Firmware debounce: 30 ms.\nExternal button shorts pins 1 and 2 only.')
    add('inputs','J4','Connector_Generic:Conn_01x04','QWIIC / STEMMA QT',70,190,
        {'1':'GND','2':'+3V3','3':'I2C_SDA','4':'I2C_SCL'},'BM04B-SRSS-TB(LF)(SN)',
        'Connector_JST:JST_SH_BM04B-SRSS-TB_1x04-1MP_P1.00mm_Vertical','JST')
    r('inputs',19,'4.7k',130,185,'+3V3','I2C_SDA')
    r('inputs',20,'4.7k',175,185,'+3V3','I2C_SCL')
    c('inputs',29,'100n',220,185,'+3V3')
    add('inputs','J5','Connector_Generic:Conn_02x05_Odd_Even','UART / SERVICE',320,190,
        {'1':'+3V3','2':'GND','3':'UART_TX','4':'GND','5':'UART_RX','6':'GND','7':'EN','8':'GND','9':'BOOT','10':'GND'},
        'FTSH-105-01-L-D','Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical','Samtec',
        'Custom UART pinout, not ARM SWD; 3.3 V is reference, do not power from debugger')
    text('inputs',20,235,'Qwiic: 1 GND, 2 3V3, 3 SDA, 4 SCL. 3.3 V only. Sensor budget <= 50 mA.\nStart at 100 kHz. Remove onboard pull-ups if parallel sensor pull-ups are too strong.\nService header: TX/RX names are from the MCU perspective. Use a 3.3 V UART adapter.\nEN and BOOT require open-drain drive. J5 is not a standard ARM debug connector.',1.65)
    write_schematics()
    write_bom()
    write_board()

def write_schematics():
    for key,sh in SHEETS.items():
        libs=[]
        for lid,s in sh['libs'].items():
            s=copy.deepcopy(s)
            s[1]=lid
            libs.append(emit(s))
        contents=f'''(kicad_sch (version 20231120) (generator "eeschema")
          (uuid {sh['uuid']}) (paper "A3")
          (title_block (title "Clearday Home") (date "2026-10-11") (rev "A")
            (company "HackNC 2026") (comment 1 {q(sh['title'])}) (comment 2 "Prototype schematic; PCB placement study is not fabrication-ready"))
          (lib_symbols {' '.join(libs)})
          {' '.join(sh['items'])}
          {'(sheet_instances (path "/" (page "1")))' if key=='power' else ''}
        )'''
        (ROOT/('clearday-home.kicad_sch' if key=='power' else key+'.kicad_sch')).write_text('\n'.join(line.rstrip() for line in contents.splitlines())+'\n')
    (ROOT/'Clearday.kicad_sym').write_text('(kicad_symbol_lib (version 20231120) (generator "kicad_symbol_editor") '+emit(CUSTOM)+'\n'+emit(AMP_SYMBOL)+')\n')
    libs=sorted({c['lib_id'].split(':')[0] for c in COMPONENTS}|{'power'})
    table=['(sym_lib_table (version 7)']
    for lib in libs:
        uri='${KIPRJMOD}/Clearday.kicad_sym' if lib=='Clearday' else '${KICAD8_SYMBOL_DIR}/'+lib+'.kicad_sym'
        table.append(f'(lib (name {q(lib)}) (type "KiCad") (uri {q(uri)}) (options "") (descr ""))')
    (ROOT/'sym-lib-table').write_text('\n'.join(table)+')\n')
    fplibs=sorted({c['footprint'].split(':')[0] for c in COMPONENTS})
    (ROOT/'fp-lib-table').write_text('(fp_lib_table (version 7)\n'+'\n'.join(
        f'(lib (name {q(lib)}) (type "KiCad") (uri "${{KICAD8_FOOTPRINT_DIR}}/{lib}.pretty") (options "") (descr ""))' for lib in fplibs)+')\n')
    project={'meta':{'filename':'clearday-home.kicad_pro','version':1},
             'net_settings':{'classes':[{'name':'Default','clearance':0.2,'track_width':0.25,'via_diameter':0.6,'via_drill':0.3,
               'diff_pair_width':0.2,'diff_pair_gap':0.15,'diff_pair_via_gap':0.25,'bus_width':12,'line_style':0,
               'wire_width':6,'microvia_diameter':0.3,'microvia_drill':0.1,'pcb_color':'rgba(0, 0, 0, 0.000)',
               'schematic_color':'rgba(0, 0, 0, 0.000)'}],'meta':{'version':3}},
             'erc':{'erc_exclusions':[],'meta':{'version':0},'rule_severities':{}},
             'board':{'design_settings':{'rules':{'min_clearance':0.2,'min_track_width':0.2,'min_via_diameter':0.6,
                'min_through_hole_diameter':0.3,'min_copper_edge_clearance':0.3},'drc_exclusions':[]}}}
    (ROOT/'clearday-home.kicad_pro').write_text(json.dumps(project,indent=2)+'\n')

def write_bom():
    grouped={}
    for cpt in COMPONENTS:
        k=(cpt['value'],cpt['mpn'],cpt['footprint'],cpt['manufacturer'],cpt['notes'])
        grouped.setdefault(k,[]).append(cpt['ref'])
    with (ROOT/'bom.csv').open('w',newline='') as f:
        w=csv.writer(f,lineterminator='\n')
        w.writerow(['References','Quantity','Value','MPN','Footprint','Manufacturer','Notes'])
        for k,refs in grouped.items():
            w.writerow([', '.join(refs),len(refs),*k])
    (ROOT/'design.json').write_text(json.dumps(COMPONENTS,indent=2)+'\n')

def write_board():
    import pcbnew as pcb
    board=pcb.BOARD()
    title=board.GetTitleBlock()
    title.SetTitle('Clearday Home')
    title.SetRevision('A')
    title.SetDate('2026-10-11')
    title.SetCompany('HackNC 2026')
    title.SetComment(0,'PLACEMENT STUDY ONLY: unrouted, do not fabricate')
    allnets=sorted({n for cpt in COMPONENTS for n in cpt['nets'].values() if n})
    netmap={}
    for name in allnets:
        n=pcb.NETINFO_ITEM(board,name)
        board.Add(n)
        netmap[name]=n
    def point(x,y):
        return pcb.VECTOR2I(pcb.FromMM(x),pcb.FromMM(y))
    edge=pcb.PCB_SHAPE()
    edge.SetShape(pcb.SHAPE_T_CIRCLE)
    edge.SetCenter(point(100,100))
    edge.SetEnd(point(135,100))
    edge.SetLayer(pcb.Edge_Cuts)
    edge.SetWidth(pcb.FromMM(0.05))
    board.Add(edge)
    # Top-side LED ring; all service components on the rear.
    placements={'U1':(100,80,180), 'J1':(100,129,0),'U2':(105,123,0),'U3':(91,115,0),
                'U4':(112,105,0),'U5':(82,96,0),'U6':(85,106,0),'MK1':(79,114,0),
                'J2':(119,113,0),'J3':(116,122,0),'J4':(80,104,0),'J5':(115,92,0),
                'SW1':(108,96,0),'SW2':(108,91,0),'SW3':(96,103,0),'C11':(78,98,0),
                'F1':(94,122,0),'D1':(89,119,0)}
    # A placement study intentionally leaves routing and detailed packing to PCB review.
    footprints=[]
    ring_angles=[-45+i*270/11 for i in range(12)]
    ring_angles[5],ring_angles[6]=70,110  # USB shell stakes need a lower gap.
    for i,cpt in enumerate(COMPONENTS):
        lib,name=cpt['footprint'].split(':')
        fp=pcb.FootprintLoad(str(FP/(lib+'.pretty')),name)
        if fp is None:
            raise RuntimeError('Missing standard footprint '+cpt['footprint'])
        board.Add(fp)
        fp.SetReference(cpt['ref'])
        fp.SetValue(cpt['value'])
        fp.SetFPID(pcb.LIB_ID(lib,name))
        fp.SetPath(pcb.KIID_PATH(cpt['path']+'/'+cpt['uuid']))
        ref=cpt['ref']
        if ref.startswith('D') and ref!='D1':
            idx=int(ref[1:])-2
            angle=math.radians(ring_angles[idx])
            x,y=100+30*math.cos(angle),100+30*math.sin(angle)
            rot=-ring_angles[idx]
        elif ref.startswith('C') and 13<=int(ref[1:])<=24:
            idx=int(ref[1:])-13
            angle=math.radians(ring_angles[idx])
            x,y=100+23.5*math.cos(angle),100+23.5*math.sin(angle)
            rot=-ring_angles[idx]
        else:
            x,y,rot=placements.get(ref,(76+(i%9)*5,86+(i//9)*4,0))
            fp.Flip(point(0,0),True)
        fp.SetPosition(point(x,y))
        fp.SetOrientationDegrees(rot)
        fp.Value().SetVisible(False)
        fp.Reference().SetTextSize(point(0.8,0.8))
        fp.Reference().SetTextThickness(pcb.FromMM(0.12))
        for pad in fp.Pads():
            net=cpt['nets'].get(pad.GetNumber())
            if net:
                pad.SetNet(netmap[net])
        footprints.append((cpt,fp))
    # Pack the rear components without intersecting courtyards. A conservative
    # cross-layer check also reserves space for through-hole parts on the front.
    def rect(fp):
        if fp.GetReference()=='U1':
            return (90.2,66.5,109.8,93.5)
        boxes=[]
        for g in fp.GraphicalItems():
            if g.GetLayer() in [pcb.F_CrtYd,pcb.B_CrtYd]:
                b=g.GetBoundingBox()
                boxes.append((pcb.ToMM(b.GetX()),pcb.ToMM(b.GetY()),
                              pcb.ToMM(b.GetRight()),pcb.ToMM(b.GetBottom())))
        if not boxes:
            b=fp.GetBoundingBox(False,False)
            return (pcb.ToMM(b.GetX()),pcb.ToMM(b.GetY()),pcb.ToMM(b.GetRight()),pcb.ToMM(b.GetBottom()))
        return min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)
    fixed=[(cpt,fp) for cpt,fp in footprints if fp.GetLayer()==pcb.F_Cu or cpt['ref'] in ['U1','J1']]
    occupied=[rect(fp) for cpt,fp in fixed]
    occupied.append((76,45,124,73.25))
    movable=[(cpt,fp) for cpt,fp in footprints if (cpt,fp) not in fixed]
    movable.sort(key=lambda v:-(rect(v[1])[2]-rect(v[1])[0])*(rect(v[1])[3]-rect(v[1])[1]))
    for cpt,fp in movable:
        ox,oy=pcb.ToMM(fp.GetPosition().x),pcb.ToMM(fp.GetPosition().y)
        b=rect(fp)
        rel=(b[0]-ox,b[1]-oy,b[2]-ox,b[3]-oy)
        candidates=[(x/2,y/2) for x in range(136,265) for y in range(148,265)]
        candidates.sort(key=lambda p:(p[0]-ox)**2+(p[1]-oy)**2)
        for x,y in candidates:
            rct=(x+rel[0],y+rel[1],x+rel[2],y+rel[3])
            if any((a-100)**2+(b-100)**2>34**2 for a in [rct[0],rct[2]] for b in [rct[1],rct[3]]):
                continue
            if any(not(rct[2]+0.3<o[0] or rct[0]-0.3>o[2] or rct[3]+0.3<o[1] or rct[1]-0.3>o[3]) for o in occupied):
                continue
            fp.SetPosition(point(x,y))
            occupied.append(rct)
            break
        else:
            raise RuntimeError('No placement space for '+cpt['ref']+' '+str(rel)+' occupied='+str(occupied))
    # Provisional ground pours. These are not a substitute for signal routing.
    for layer in [pcb.F_Cu,pcb.B_Cu]:
        zone=pcb.ZONE(board)
        zone.SetLayer(layer)
        zone.SetNet(netmap['GND'])
        zone.SetLocalClearance(pcb.FromMM(0.25))
        zone.SetThermalReliefGap(pcb.FromMM(0.3))
        zone.SetThermalReliefSpokeWidth(pcb.FromMM(0.3))
        poly=zone.Outline()
        poly.NewOutline()
        for i in range(96):
            a=2*math.pi*i/96
            p=point(100+34.5*math.cos(a),100+34.5*math.sin(a))
            poly.Append(p.x,p.y)
        board.Add(zone)
    # The standard ESP32 footprint carries a both-layer antenna keepout.
    for value,y in [('CLEARDAY HOME / REV A',101),('PLACEMENT ONLY - DO NOT FABRICATE',104)]:
        t=pcb.PCB_TEXT(board)
        t.SetText(value)
        t.SetPosition(point(100,y))
        t.SetTextSize(point(1,1))
        t.SetTextThickness(pcb.FromMM(0.15))
        t.SetLayer(pcb.F_SilkS)
        board.Add(t)
    # Reload to bind project/netclass settings before the KiCad 8 zone filler.
    pcb.SaveBoard(str(ROOT/'clearday-home.kicad_pcb'),board)
    board=pcb.LoadBoard(str(ROOT/'clearday-home.kicad_pcb'))
    board.BuildConnectivity()
    filler=pcb.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcb.SaveBoard(str(ROOT/'clearday-home.kicad_pcb'),board)

if __name__ == '__main__':
    build()
