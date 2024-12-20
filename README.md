# bletest


This program emulates a shell client (mostly written with the help of chatgpt) and uses the FFF1(notifications) and FFF2(write) UUID characteristics (asynchronous event-driven) BLE interface from the OBDLink CX to establish connection between this device and the CX. 

### Issues
Data race
Queuing and buffer aynchronous input while processing on client-side
BLE MTU