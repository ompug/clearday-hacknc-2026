#!/usr/bin/env python3
"""Check the exported schematic connectivity against board pads and requirements."""
from pathlib import Path
import json
import xml.etree.ElementTree as ET
import pcbnew

root=Path(__file__).resolve().parent
tree=ET.parse(root/'clearday-home.xml')
nets={}
for net in tree.findall('./nets/net'):
    for node in net.findall('node'):
        nets[node.attrib['ref'],node.attrib['pin']]=net.attrib['name']

def same(name,*pins):
    for ref,pin in pins:
        assert nets[ref,str(pin)]==name,(name,ref,pin,nets.get((ref,str(pin))))

same('USB_DP',('U1',14),('R3',2))
same('USB_DN',('U1',13),('R4',2))
same('USB_DP_CONN',('J1','A6'),('J1','B6'),('U2',1))
same('USB_DN_CONN',('J1','A7'),('J1','B7'),('U2',3))
same('I2S_BCLK',('U1',18),('U4',16),('MK1',4))
same('I2S_LRCLK',('U1',19),('U4',14),('MK1',1))
same('I2S_DOUT',('U1',20),('U4',1))
same('I2S_DIN',('U1',21),('MK1',6))
same('GND',('U1',41),('U4',17),('MK1',2),('J4',1))
same('SPK_P',('U4',9),('J2',1))
same('SPK_N',('U4',10),('J2',2))
same('LED_DATA',('U1',4),('U5',2))
same('BTN_ACK',('U1',5),('R17',2),('R18',2),('C28',1))
same('I2C_SDA',('U1',12),('J4',3),('R19',2))
same('I2C_SCL',('U1',17),('J4',4),('R20',2))
for pin in ['15','16','26','28','29','30']:
    assert nets.get(('U1',pin),'unconnected-').startswith('unconnected-'),pin
for i in range(12):
    same('+5V_LED',(f'D{i+2}',1),(f'C{i+13}',1))
    same('GND',(f'D{i+2}',3),(f'C{i+13}',2))
    if i<11:
        same(f'PIXEL_{i+1}',(f'D{i+2}',2),(f'D{i+3}',4))

board=pcbnew.LoadBoard(str(root/'clearday-home.kicad_pcb'))
components={c.attrib['ref']:c for c in tree.findall('./components/comp')}
assert len(components)==len(list(board.GetFootprints()))
checked=0
for fp in board.GetFootprints():
    ref=fp.GetReference()
    assert ref in components,ref
    fields={f.attrib['name']:f.text for f in components[ref].findall('./fields/field')}
    assert fields.get('MPN'),ref
    for pad in fp.Pads():
        pin=pad.GetNumber()
        if not pin:
            continue
        expected=nets.get((ref,pin),'')
        actual=pad.GetNetname()
        if expected.startswith('unconnected-'):
            expected=''
        assert actual==expected,(ref,pin,actual,expected)
        checked+=1
report={'kicad_version':pcbnew.Version(),'components':len(components),'pads_checked':checked,
        'result':'PASS','checks':['Native USB polarity and duplicated connector pins','Shared I2S clocks and separate data',
        'Speaker BTL and grounded exposed pads','Twelve LED chain and per-pixel decoupling',
        'Strapping and PSRAM pins unused','I2C pinout and active-low button','Every numbered PCB pad matches exported schematic',
        'Every BOM component has an MPN'],'limitations':'Connectivity only; does not certify routing, thermal performance or USB compliance.'}
(root/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
