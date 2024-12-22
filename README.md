# bletest


This program emulates a shell client (mostly written with the help of chatgpt) and uses the FFF1(notifications) and FFF2(write) UUID characteristics (asynchronous event-driven) BLE interface from the OBDLink CX to establish connection between this device and the CX. 

BLE communication with this device is event driven and asynchronous

### Issues
Data race issues on printing due, need to implement timeout when sending commands.

Queuing and buffer aynchronous input while processing on client-side

BLE MTU negotiation - if low MTU then some info will be lost on write and read (notification)

If request data is larger than MTU then we need to reject it or split it into separate writes