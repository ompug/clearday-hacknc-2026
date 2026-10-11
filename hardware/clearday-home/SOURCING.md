# Sourcing and electrical references

Checked 2026-10-11. Stock is a snapshot, not a reservation. Quantities below
come from opened distributor pages unless marked as indexed evidence.

| Selected MPN | Evidence |
| --- | --- |
| ESP32-S3-WROOM-1-N8R8 | [TME](https://www.tme.eu/en/details/esp32s3-wrm1-8r8/iot-wifi-bluetooth-modules/espressif/esp32-s3-wroom-1-n8r8/): 3,419 in stock. LCSC and one DigiKey listing were out of stock when opened. |
| AP7361C-33E-13 | [LCSC C500795](https://www.lcsc.com/product-detail/C500795.html): 2,999 in stock. |
| MAX98357AETE+T | [LCSC C910544](https://www.lcsc.com/product-detail/C910544.html): 32,344 in stock. |
| ICS-43434 | [LCSC C5656610](https://www.lcsc.com/product-detail/C5656610.html): 149 in stock. Limited supply; recheck lifecycle before a production build. |
| TPS22918DBVR | [LCSC C131941](https://www.lcsc.com/product-detail/C131941.html): 2,660 in stock. |
| SN74AHCT1G125DBVR | [LCSC C7484](https://www.lcsc.com/product-detail/Buffer-Driver-Transceiver_Texas-Instruments-SN74AHCT1G125DBVR_C7484.html): indexed page showed 21,885 in stock. |
| WS2812B-V5/W | [LCSC C2874885](https://www.lcsc.com/product-detail/C2874885.html): indexed listing showed 79,540 in stock; recheck exact V5/W revision before purchase. |
| USB4105-GF-A | [LCSC C3020560](https://lcsc.com/product-detail/USB-Connectors_Global-Connector-Technology-USB4105-GF-A_C3020560.html): indexed listing showed 774 in stock; this evidence is older than the opened pages. |

The BOM uses specified Yageo 0603 resistors, Murata ceramic capacitors,
Panasonic EEU-FR1A102 reservoir, Littelfuse 1206L200/6 PTC, Lite-On
LTST-C190KGKT indicator, Omron switches, JST connectors, and Samtec
FTSH-105-01-L-D service header. Their exact live stock counts were not all
independently confirmed. Revalidate the complete BOM before ordering;
do not treat this as an all-lines procurement guarantee. Connector housing,
crimps, speaker, enclosure, and USB supply are outside the PCB BOM.

Electrical decisions were checked against these manufacturer documents:

- [Espressif module datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf):
  module pad numbers, native USB pins, N8R8 octal-PSRAM pin reservation,
  strapping pins, and antenna clearance.
- [Diodes AP7361C datasheet](https://www.diodes.com/datasheet/download/AP7361C.pdf):
  fixed 3.3 V, SOT-223 pinout and grounded tab, capacitor requirements,
  current and thermal limits.
- [Analog Devices MAX98357A/B datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX98357A-MAX98357B.pdf):
  TQFN pinout, grounded exposed pad, SD_MODE channel thresholds, gain
  selection, I2S frame format, and differential speaker output. At a nominal
  3.3 V GPIO, 560 kΩ into the internal 100 kΩ gives 0.500 V, inside the
  mixed-channel window. The +3 dB gain resistor goes to VDD, not ground.
- [TDK ICS-43434 datasheet](https://invensense.tdk.com/wp-content/uploads/2016/02/DS-000069-ICS-43434-v1.2.pdf):
  pinout, supply, left-slot selection, clock range, and acoustic port.
- [TI TPS22918 datasheet](https://www.ti.com/lit/ds/symlink/tps22918.pdf):
  DBV pins 1 VIN, 2 GND, 3 ON, 4 CT, 5 QOD, 6 VOUT. A 10 nF timing capacitor
  gives approximately 26.55 ms rise at 5 V. QOD is left open because the
  1000 µF load exceeds the direct-QOD capacitor limit.
- [Samtec FTSH-105-01-L-D](https://www.samtec.com/products/ftsh-105-01-l-d):
  ten-position, two-row, 1.27 mm through-hole service header.

The shared I2S clocks, GPIO allocation, conservative power budget, and
placement choices are design decisions made here. Bench testing remains
necessary; an ERC pass checks schematic rules, not electrical performance.
