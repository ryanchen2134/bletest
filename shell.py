import asyncio
from bleak import BleakClient, BleakScanner, BleakError

DEVICE_NAME = "OBDLink CX"
FFF1_NOTIFY_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"  # Notification
FFF2_WRITE_UUID = "0000fff2-0000-1000-8000-00805f9b34fb"  # Write
PRINT_QUEUE = asyncio.Queue()  # Use asyncio.Queue for async operations


class MultiFrameBuffer:
    def __init__(self):
        self.buffer = bytearray()
        self.expected_length = None  # Total payload length for multi-frame
        self.current_length = 0      # Bytes received so far

    def append(self, data: bytearray):
        """
        Append data to the buffer and update the expected length.
        """
        print(f"Received Data: {data.hex()}")

        if len(data) == 0:
            return  # Ignore empty frames

        if self.expected_length is None:
            # Single-frame response or first frame
            self.expected_length = len(data)  # Treat the frame as complete
            self.buffer.extend(data)
            self.current_length = len(data)
            print(f"Single Frame Detected: Length = {self.expected_length}")
        else:
            # Multi-frame response: append payload
            self.buffer.extend(data)
            self.current_length += len(data)
            print(f"Consecutive Frame: Current Length = {self.current_length}")

    def is_complete(self):
        """
        Check if the full message has been received.
        """
        print(f"Checking Completion: Expected = {self.expected_length}, Current = {self.current_length}")
        return self.expected_length is not None and self.current_length >= self.expected_length

    def extract(self):
        """
        Extract the complete message and reset the buffer.
        """
        if not self.is_complete():
            return None
        complete_message = self.buffer[:self.expected_length]
        self.reset()
        return complete_message

    def reset(self):
        """
        Reset the buffer for the next message.
        """
        print("Resetting MultiFrameBuffer.")
        self.buffer = bytearray()
        self.expected_length = None
        self.current_length = 0




multi_frame_buffer = MultiFrameBuffer()


async def enqueue_output(*args, **kwargs):
    """
    Add a message to the print queue.
    """
    message = " ".join(map(str, args))
    await PRINT_QUEUE.put(message)


async def output_handler():
    """
    Continuously process messages from the print queue and display them.
    """
    try:
        while True:
            message = await PRINT_QUEUE.get()  # Wait for a message
            if message is None:
                break  # Graceful shutdown
            print(message, flush=True)  # Print the message immediately
            PRINT_QUEUE.task_done()  # Mark the task as done
    except Exception as e:
        print(f"Error in output_handler: {e}")
    finally:
        print("Output handler stopped.")



async def notification_handler(sender, data: bytearray):
    """
    Async notification handler to process incoming data.
    """
    print(f"Notification from {sender.uuid}: {data.hex()}")

    # Append data to the buffer
    multi_frame_buffer.append(data)

    # Check for completeness
    if multi_frame_buffer.is_complete():
        complete_message = multi_frame_buffer.extract()
        await enqueue_output(f"[Complete Response] {complete_message.decode('utf-8', errors='ignore')}")


async def write_with_response(client, data: bytes):
    """
    Write data to FFF2 and wait for acknowledgment.
    """
    try:
        await client.write_gatt_char(FFF2_WRITE_UUID, data, response=True)
        await enqueue_output(f"Write successful: {data.decode('utf-8', errors='ignore')}")
    except Exception as e:
        await enqueue_output(f"Error during write: {e}")


async def write_in_chunks(client, data: bytes):
    """
    Write data in chunks, respecting the negotiated MTU size.
    """
    mtu_size = client.mtu_size - 3  # BLE overhead reduces usable bytes
    for i in range(0, len(data), mtu_size):
        chunk = data[i:i + mtu_size]
        await enqueue_output(f"Writing chunk: {chunk}")
        await write_with_response(client, chunk)
        await asyncio.sleep(0.1)  # Small delay to avoid overwhelming the device


async def initialize_device(client):
    """
    Initialize the OBDLink CX with commands based on the iOS app's initialization workflow.
    """
    commands = [
        "ATZ",         # Reboot the device
        # "ATPPS",       # Get programmable parameter summary
        "ATWS",        # Warm start (mini reboot)
        # "ATE0",        # Disable echo
        "ATM0",        # Disable memory
        "ATS0",        # Disable space printing
        "ATAT1",       # Enable adaptive timing
        "ATH1",        # Enable headers
        "ATSP7",       # Set protocol: ISO 15765-4 (CAN 29-bit, 500 kbps)
        "ATS0",        # Disable space printing again
        # "ATSH DB33F1", # Set CAN header
        "ATAR",        # Automatically set receive address
        "ATFCSM 0"     # Set flow control mode to automatic
    ]

    for command in commands:
        try:
            await enqueue_output(f"Sending initialization command: {command}")
            await write_in_chunks(client, f"{command}\r".encode("utf-8"))
        except Exception as e:
            await enqueue_output(f"Error sending command {command}: {e}")


async def interactive_shell(client):
    """
    Interactive shell to send commands to FFF2 and handle responses from FFF1.
    """
    await enqueue_output("\nInteractive Shell (type `exit` to quit):")
    while True:
        await enqueue_output("# ", end="", flush=True)  # Print prompt through queue
        command = await asyncio.to_thread(input)  # Non-blocking input
        if command.lower() == "exit":
            await enqueue_output("Exiting interactive shell...")
            break

        # Encode command and write in chunks
        command_bytes = (command + "\r").encode("utf-8")  # Append carriage return
        try:
            await write_in_chunks(client, command_bytes)
            await enqueue_output(f"Sent: {command}")
        except BleakError as e:
            await enqueue_output(f"Error sending command: {e}")
        except KeyboardInterrupt:
            await enqueue_output("KeyboardInterrupt: Exiting interactive shell...")
            break


async def connect_and_enable_notifications(device_name: str):
    """
    Discover, connect, enable notifications, and handle multi-frame responses.
    """
    await enqueue_output("Scanning for devices...")
    devices = await BleakScanner.discover()
    target_device = None

    for device in devices:
        await enqueue_output(f"Found device: {device.name}, Address: {device.address}")
        if device.name == device_name:
            target_device = device
            break

    if not target_device:
        await enqueue_output(f"Device '{device_name}' not found. Exiting.")
        return

    await enqueue_output(f"Connecting to {device_name} at {target_device.address}...")
    try:
        async with BleakClient(target_device.address) as client:
            await enqueue_output("Connected successfully.")
            await enqueue_output(f"Negotiated MTU size: {client.mtu_size} bytes.")

            # Enable notifications
            await enqueue_output(f"Subscribing to notifications on {FFF1_NOTIFY_UUID}...")
            await client.start_notify(FFF1_NOTIFY_UUID, notification_handler)
            await enqueue_output("Notifications enabled.")

            # Run initialization asynchronously
            await initialize_device(client)

            # Start the interactive shell
            await interactive_shell(client)

            # Stop notifications
            await enqueue_output("Stopping notifications...")
            await client.stop_notify(FFF1_NOTIFY_UUID)
            await enqueue_output("Notifications stopped. Disconnected.")

    except BleakError as e:
        await enqueue_output(f"An error occurred: {e}")


async def main():
    # Start the output handler
    output_task = asyncio.create_task(output_handler())

    # Run the connection process
    await connect_and_enable_notifications(DEVICE_NAME)

    # Stop the output handler
    await PRINT_QUEUE.put(None)  # Signal output handler to stop
    await output_task  # Wait for output handler to finish


if __name__ == "__main__":
    asyncio.run(main())
