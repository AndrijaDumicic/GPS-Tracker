from machine import Pin, UART, I2C
import utime
from micropyGPS import MicropyGPS


gps_module = UART(1, baudrate=9600, tx=Pin(4), rx=Pin(5))
time_zone = -3
gps = MicropyGPS(time_zone)


sim800l_module = UART(0, baudrate=9600, tx=Pin(12), rx=Pin(13))


i2c = I2C(0, scl=Pin(1), sda=Pin(0), freq=400000)

print('Scanning I2C bus...')
devices = i2c.scan()

if devices:
    print('I2C devices found:', devices)
else:
    print('No I2C devices found')

utime.sleep(2)

destination_phone = '+385919738960'

led = Pin(25, Pin.OUT)

blue = Pin(20, Pin.OUT)

yellow = Pin(18, Pin.OUT)

red = Pin(16, Pin.OUT)

green = Pin(17, Pin.OUT)


# BQ27441 Constants
BQ27441_ADDR = 0x55

# BQ27441 Registers
CONTROL_REG = 0x00
TEMPERATURE_REG = 0x02
VOLTAGE_REG = 0x04
STATE_OF_CHARGE_REG = 0x1C

def read_bq27441_register(register):
    try:
        i2c.writeto(BQ27441_ADDR, bytes([register]))
        utime.sleep_ms(10)  
        result = i2c.readfrom(BQ27441_ADDR, 2)
        return int.from_bytes(result, 'little')
    except Exception as e:
        print("Error reading from BQ27441 register:", e)
        return None

def get_battery_voltage():
    voltage = read_bq27441_register(VOLTAGE_REG)
    if voltage is not None:
        return voltage / 1000  
    else:
        print("Failed to read battery voltage.")
        return None

def get_battery_soc():
    soc = read_bq27441_register(STATE_OF_CHARGE_REG)
    if soc is not None:
        return soc
    else:
        print("Failed to read battery state of charge.")
        return None


def blink_led(times):
    for _ in range(times):
        led.on()
        utime.sleep(1)
        led.off()
        utime.sleep(1)

def check_sim800l_status():
    sim800l_module.write('AT+CREG?\r')  # Check network registration
    utime.sleep(5)
    response = sim800l_module.read()
    if response is None:
        print("SIM800L not registered to network.")
        return False
    else:
        return True

def convert_coordinates(sections):
    if sections[0] == 0:  # sections[0] contains the degrees
        return None

    # sections[1] contains the minutes
    data = sections[0] + (sections[1] / 60.0)

    # sections[2] contains 'E', 'W', 'N', 'S'
    if sections[2] == 'S':
        data = -data
    if sections[2] == 'W':
        data = -data

    data = '{0:.6f}'.format(data)  
    return str(data)

def clear_sim_memory():
    sim800l_module.write('AT+CMGD=1,4\r') 
    utime.sleep(5)  
    response = sim800l_module.read()
    if response:
        print("Response to AT+CMGD=1,4:", response.decode('utf-8').strip())
    else:
        print("No response for clear SIM memory command.")

def check_sim_memory():
    sim800l_module.write('AT+CPMS?\r')
    utime.sleep(5)
    response = sim800l_module.read()
    if response:
        print("SIM Memory Status:", response.decode('utf-8').strip())
    else:
        print("No response for SIM memory check.")

def send_sms_with_location(number, latitude, longitude, note=""):
    blink_led(2)  
    google_maps_link = 'https://www.google.com/maps/place/{},{}'.format(latitude, longitude)
    message = '{}\nLatitude: {}\nLongitude: {}\nLocation Link: {}\nBattery Voltage: {}V\nBattery SOC: {}%'.format(
        note, latitude, longitude, google_maps_link, get_battery_voltage(), get_battery_soc()
    )

    sim800l_module.write('AT+CMGF=1\r') 
    utime.sleep(1)
    sim800l_module.write('AT+CMGS="{}"\r'.format(number))
    utime.sleep(1)
    sim800l_module.write(message + '\r')
    utime.sleep(1)
    sim800l_module.write(chr(26)) 
    utime.sleep(3)  

    response = sim800l_module.read()
    if b'OK' in response or b'> ' in response:
        print("SMS sent successfully.")
        utime.sleep(5) 
        clear_sim_memory()
    else:
        print("Failed to send SMS. Response: ", response)

def send_sms(number, message):
    blink_led(2)  
    sim800l_module.write('AT+CMGF=1\r')  
    utime.sleep(1)
    sim800l_module.write('AT+CMGS="{}"\r'.format(number))
    utime.sleep(1)
    sim800l_module.write(message + '\r')
    utime.sleep(1)
    sim800l_module.write(chr(26))  
    utime.sleep(3)  

    response = sim800l_module.read()
    if b'OK' in response or b'> ' in response:
        print("SMS sent successfully.")
        utime.sleep(5)  
        clear_sim_memory()
    else:
        print("Failed to send SMS. Response: ", response)


stored_latitude = None
stored_longitude = None

def store_gps_coordinates():
    global stored_latitude, stored_longitude
    length = gps_module.any()
    if length > 0:
        data = gps_module.read(length)
        for byte in data:
            gps.update(chr(byte))

        latitude = convert_coordinates(gps.latitude)
        longitude = convert_coordinates(gps.longitude)

        if latitude is not None and longitude is not None:
            stored_latitude = latitude
            stored_longitude = longitude
            red.on()
            return True  
    return False  

def handle_incoming_message():
    global stored_latitude, stored_longitude
    if sim800l_module.any():
        yellow.off()
        battery_voltage = get_battery_voltage()
        battery_soc = get_battery_soc()
        gps_signal = store_gps_coordinates()
        
        if gps_signal:
            note = "This is the current location."
        else:
            note = "This is the last known location."

        if stored_latitude is None or stored_longitude is None:
            send_sms(destination_phone, "GPS coordinates unavailable.\nBattery Voltage: {}V\nBattery SOC: {}%".format(battery_voltage, battery_soc))
        else:
            print('Stored Lat: ' + stored_latitude)
            print('Stored Lon: ' + stored_longitude)
            send_sms_with_location(destination_phone, stored_latitude, stored_longitude, note)  
            stored_latitude = None 
            stored_longitude = None
            red.off()

        utime.sleep(5)   
        clear_sim_memory()
        check_sim_memory()  
        
blue.on() 

while not check_sim800l_status():
    print("Retrying SIM800L initialization...")
    utime.sleep(3)  

print("SIM800L initialized successfully.")
clear_sim_memory()
check_sim_memory() 
blue.off()


led_state = False
last_toggle_time = utime.ticks_ms()
toggle_interval = 500  

while True:
    current_time = utime.ticks_ms()
    if utime.ticks_diff(current_time, last_toggle_time) >= toggle_interval:
        led_state = not led_state
        yellow.value(led_state)
        last_toggle_time = current_time
    
    store_gps_coordinates()
    handle_incoming_message() 
    utime.sleep_ms(100)  

