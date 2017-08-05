import os
import re
import datetime
import threading
from queue import Queue

def _lib_install(lib):
    try:
        os.system('pip install ' + str(lib))
    except:
        pass

try:
    import netmiko
except ModuleNotFoundError:
    _lib_install('netmiko')
    import netmiko

def _get_ip_list_files(dir):
    files = []
    final_files = []
    for (dirpath, dirnames, filenames) in os.walk(dir):
        files.extend(filenames)
    for file in files:
        name, extension = os.path.splitext(file)
        if ((extension == '.csv') | (extension == '.txt')):
            final_files.append(file)
    return final_files

def _choose_ip_list_file():
    ip_list_files = _get_ip_list_files(working_dir)
    if len(ip_list_files) == 0: print('No .csv or .txt files found in ' + working_dir + '\n' + 'Exiting.')
    i = 0
    for f in ip_list_files:
        print ('[' + str(i) + '] ' + f)
        i += 1
    while True:
        try:
            if len(ip_list_files) == 1:
                print('Only one file found ({0!s}). It will be chosen automatically.'.format(ip_list_files[0]))
                selected_file = ip_list_files[0]
                break
            else:
                print("Choose file with IP addresses(0-{0})".format(len(ip_list_files)-1))
                selected_file = ip_list_files[int(input())]
                break
        except Exception as e:
            print('ERROR', e)
            continue
    return selected_file

def _is_valid_IP(strng):
    if re.search(
            '^(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\.'
            '(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\.'
            '(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\.'
            '(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])$',
            strng) != None:
        return True
    return False

def read_file_to_list(file):
    try:
        print('Reading ',file)
        file_obj = open(file, "r")
        ip_list = file_obj.readlines()
        file_obj.close()
        #	Strip EOL symbols
        for i in range(0, len(ip_list)):
            ip_list[i]=ip_list[i].rstrip()
        print('Checking IP address validity')
        i = 0
        while i < len(ip_list):
            if not _is_valid_IP(ip_list[i]) or int(ip_list[i].split('.')[0])>223:
                print(ip_list[i], 'is not a valid unicast IP address. Excluding.')
                del ip_list[i]
            else:
                i += 1
        print(ip_list)
        return ip_list
    except Exception as e:
        print('Error opening hosts file')
        print(e)
        return('ERROR')

def filter_by_conn(devices):
    # Filter devices list, leaving only devices that respond to connection over specified protocol
    def filt_threader():
        while True:
            worker_device = filt_q.get()
            if worker_device.check_connection() == False:
                devices.remove(worker_device)
            filt_q.task_done()

    filt_q = Queue()

    if common_devices_type == 'cisco_ios':
        protocol = 'ssh'
    elif common_devices_type == 'cisco_ios_telnet':
        protocol = 'telnet'

    print('Checking connections to devices over', protocol)

    for x in range(number_of_threads):
        filt_t = threading.Thread(target=filt_threader)
        filt_t.daemon = True
        filt_t.start()

    for device in devices:
        filt_q.put(device)

    filt_q.join()
    return (devices)

def threader():
    while True:
        worker = q.get()
        action(worker)
        q.task_done()

def action(device):
    print('Connecting to', device.mgmt_ip)
    print('Wiping output file')
    device.wipe_output_file()
    print('Gathering info from ', device.mgmt_ip)
    data_dict = device.get_info(['show run', 'show version'])
    print('Saving info to file')
    device.save_info_to_file(data_dict)

class Device:
    def __init__(self, mgmt_ip, dev_type, username, password, en_password):
        self.mgmt_ip = mgmt_ip
        self.dev_type = dev_type
        self.username = username
        self.password = password
        self.en_password = en_password
        self.output_file_name = ''

    def check_connection(self):
        try:
            print('Trying to connect to ', self.mgmt_ip)
            netmiko.ConnectHandler(
                ip=self.mgmt_ip, device_type=self.dev_type, username=self.username, password=self.password)
            print('Success!')
            return True
        except Exception as e:
            print('ERROR! ', str(e))
            return False

    def get_info(self, commands):
        # Getting show output
        # List of commands as input
        output = {}
        connection = netmiko.ConnectHandler(
            ip=self.mgmt_ip, device_type=self.dev_type, username=self.username, password=self.password, secret=self.en_password)
        connection.enable()
        for command in commands:
            output[command] = connection.send_command(command)
        return output

    def fetch_name(self):
        return self.get_info(['show run | inc hostname'])['show run | inc hostname'].split()[1]

    def wipe_output_file(self):
        self.output_file_name = os.path.join(output_path, self.fetch_name() + '.log')
        self.output_file = open(self.output_file_name, "w")
        self.output_file.close()

    def save_info_to_file(self, data_dict):
        self.output_file = open(self.output_file_name, "a")
        for command in data_dict:
            self.output_file.writelines(command + '\n' + '-'*75 + '\n'*2)
            self.output_file.writelines(data_dict[command])
            self.output_file.writelines('\n' + '='*75 + '\n'*3)
        self.output_file.close()

#Initializing variables
working_dir = os.getcwd()
number_of_threads = 3
common_devices_type = 'cisco_ios'
username = 'test'
password = 'cisco'
enable_password = 'cisco'
commands_list = ['show runn']
working_ip_list_file = os.path.join(working_dir,_choose_ip_list_file())
ip_addr_list = read_file_to_list(working_ip_list_file)

#Create folder to save output
output_path = os.path.join(working_dir,'results_'+datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
if not os.path.exists(output_path): os.makedirs(output_path)

#Instantiating devices objects
devices = [Device(ip_addr,common_devices_type, username, password, enable_password) for ip_addr in ip_addr_list]

#Remove devices that don't respond on specified protocol respond from list
devices = filter_by_conn(devices)

q = Queue()

for x in range(number_of_threads):
    t = threading.Thread(target=threader)
    t.daemon = True
    t.start()

for device in devices:
    q.put(device)

q.join()
