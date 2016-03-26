#!/usr/bin/env python
# Azure routines...
# Based and inspired by the tool VMSSDashboard from Guy Bowerman - Copyright (c) 2016.

"""
Copyright (c) 2016, Marcelo Leal
Description: The power is in the terminal...
License: MIT (see LICENSE.txt file for details)
"""

import sys
import time
import json
import azurerm
import threading
import platform
import logging
from logtail import *
from unicurses import *
from windows import *
from datacenters import *

# Load Azure app defaults
try:
	with open('vmssconfig.json') as configFile:
		configData = json.load(configFile)
except FileNotFoundError:
	print("Error: Expecting vmssconfig.json in current folder")
	sys.exit()

#Read the config params...
tenant_id = configData['tenantId']
app_id = configData['appId']
app_secret = configData['appSecret']
subscription_id = configData['subscriptionId']
# this is the resource group, VM Scale Set to monitor..
rgname = configData['resourceGroup']
vmssname = configData['vmssName']
vmsku = configData['vmSku']
tier = configData['tier']
purgeLog = configData['purgeLog']
logName = configData['logName']
logLevel = configData['logLevel']
interval = configData['interval']
configFile.close()

#Region...
region=""

#Just a high number, so we can test and see if it was not updated yet...
capacity=999999
#VM
vm_selected = [999999, 999999];

#Window VM
countery=0
window_vm = []; panel_vm = []; instances_deployed = [];
vm_details = ""; vm_nic = "";
page = 1;

#Flag to quit...
quit = 0;

#Remove old log file if requested (default behavior)...
if (purgeLog == "Yes"):
	if (os.path.isfile(logName)):
		os.remove(logName);

#Basic Logging...
#logging.basicConfig(format='%(asctime)s - %(levelname)s:%(message)s', datefmt='%H:%M:%S', level=logLevel, filename=logName)
logging.basicConfig(format='%(asctime)s - %(levelname)s:%(message)s', level=logLevel, filename=logName)

#Exec command...
def exec_cmd(window, access_token, cap, cmd):
	global subscription_id, rgname, vmssname, vmsku, tier, vm_selected, window_vm, panel_vm, vm_details, vm_nic, page;

	#Return codes...
	initerror = 2; syntaxerror = 3; capacityerror = 4;
	execsuccess = 0; execerror = 1;

	#Sanity check on capacity...
	if (cap == "999999"):
		return initerror;
	if not (isinstance(cap, int)):
		return initerror;

	#Syntax check...
	if (len(cmd.split()) != 4 and len(cmd.split()) != 3):
		return syntaxerror;

	counter = 0;
	for c in cmd.split():
		if (counter == 0):
			if (c == "add" or c == "del" or c == "rg" or c == "select" or c == "show"):
				op = c;
			else:
				return syntaxerror;
		if (counter == 1 and op == "show" and c != "page"):
				return syntaxerror;
		if (counter == 1 and c != "vm") and (op == "add" or op == "del" or op == "select"):
			return syntaxerror;
		if (counter == 1 and op == "rg"):
			rgname_new = c;
		if (counter == 2) and (op == "add" or op == "del" or op == "select" or op == "show"): 
			try:
				a = int(c) + 1;
				qtd = int(c);
			except:
				return syntaxerror;
		if (counter == 2 and op == "select"):
			z = 0; ifound = 0;
			while (z < instances_deployed.__len__()):
				if (instances_deployed[z] == int(c)):
					ifound = 1;
					break;
				z += 1;
			if (ifound):
				vm = int(c);
			else:
				return syntaxerror;
		if (counter == 2 and op == "rg" and c != "vmss"):
				return syntaxerror;
		if (counter == 2 and op == "show"):
			try:
				a = int(c) + 1;
				if (int(c) == page):
					return execsuccess; 
				if (int(c) > 1):
					b = ((window_vm.__len__() / (int(c) - 1)));
					if (b <= 100 or (int(c)) <= 0):
						return syntaxerror;
					else:
						page_new = int(c);
				elif (int(c) == 1):
						page_new = int(c);
				else:
						return syntaxerror;
			except:
				return syntaxerror;
		if (counter == 3 and op == "rg"):
			vmssname_new = c;
		counter += 1;

	#Execution...
	if (op == "add" or op == "del"):
		if (qtd > 9): 
			return capacityerror;
		#Scale-in or Scale-out...
		if (op == "add"):
   			newCapacity = cap + int(c);
		else:
   			newCapacity = cap - int(c);
		#Ok, everything seems fine, let's do it...
		#Change the VM scale set capacity by 'qtd' (can be positive or negative for scale-out/in)
		scaleoutput = azurerm.scale_vmss(access_token, subscription_id, rgname, vmssname, vmsku, tier, newCapacity);
		if (scaleoutput.status_code == 200):
			return execsuccess;
		else:
			return execerror;
	elif (op == "select"):
		vm_selected[1] = vm_selected[0];
		vm_selected[0] = vm;
		vm_details_old = vm_details; vm_nic_old = vm_nic;
		vm_details = azurerm.get_vmss_vm_instance_view(access_token, subscription_id, rgname, vmssname, vm_selected[0]);
		#vm_nic = azurerm.get_vmss_vm_nics(access_token, subscription_id, rgname, vmssname, vm_selected[0]);
		#if (len(vm_details) > 0 and len(vm_nic) > 0):
		if (len(vm_details) > 0):
			return execsuccess;
		else:
			vm_details = vm_details_old;
			vm_nic = vm_nic_old;
			vm_selected[1] = 999998;
			return execerror;
	elif (op == "show"):
		unset_page();
		set_page(window, page_new);
		return execsuccess;
	else:
		#Test to be sure the resource group and vmss provided do exist...
		rgoutput = azurerm.get_vmss(access_token, subscription_id, rgname_new, vmssname_new);
		try:
			test = rgoutput['location'];
			rgname = rgname_new; vmssname = vmssname_new;
			#Just a flag for us to know that we changed the vmss and need to deselect any VM...
			vm_selected[1] = 999998;
			page = 1;
			return execsuccess;
		except:
			return execerror;

def unset_page():
	global page, window_vm, panel_vm;
	old_page = page;

	vmlimit = int(window_vm.__len__());
	blimit = int(int(old_page) * 100);
	b = (blimit - 100);
	while (b < blimit and b < vmlimit):
		hide_panel(panel_vm[b]);
		b += 1;

def set_page(window, page_new):
	global page, window_vm, panel_vm;
	page = page_new;
	snap_page = "%02d" % page_new;

	vmlimit = int(window_vm.__len__());
	blimit = int(int(page) * 100);
	b = (blimit - 100);
	while (b < blimit and b < vmlimit):
		show_panel(panel_vm[b]);
		b += 1;
	write_str(window['virtualmachines'], 31, 45, snap_page);
	update_panels();
	doupdate();

def fill_quota_info(window, quota):
	write_str(window['usage'], 2, 23, quota['value'][0]['currentValue']);
	write_str_color(window['usage'], 2, 29, quota['value'][0]['limit'], 7, 0);
	draw_gauge(window['gaugeas'], quota['value'][0]['currentValue'], quota['value'][0]['limit']);

	write_str(window['usage'], 3, 23, quota['value'][1]['currentValue']);
	write_str_color(window['usage'], 3, 29, quota['value'][1]['limit'], 7, 0);
	draw_gauge(window['gaugerc'], quota['value'][1]['currentValue'], quota['value'][1]['limit']);

	write_str(window['usage'], 4, 23, quota['value'][2]['currentValue']);
	write_str_color(window['usage'], 4, 29, quota['value'][2]['limit'], 7, 0);
	draw_gauge(window['gaugevm'], quota['value'][2]['currentValue'], quota['value'][2]['limit']);

	write_str(window['usage'], 5, 23, quota['value'][3]['currentValue']);
	write_str_color(window['usage'], 5, 29, quota['value'][3]['limit'], 7, 0);
	draw_gauge(window['gaugess'], quota['value'][3]['currentValue'], quota['value'][3]['limit']);

def fill_vmss_info(window, vmssget, net):
	(name, capacity, location, offer, sku, provisioningState, dns, ipaddr) = set_vmss_variables(vmssget, net);

	write_str(window['vmss_info'], 2, 14, rgname.upper());
	write_str(window['vmss_info'], 2, 48, vmssname.upper());
	write_str(window['vmss_info'], 2, 76, tier.upper());
	write_str(window['vmss_info'], 3, 37, location.upper());
	write_str(window['vmss_info'], 3, 76, vmsku);
	write_str(window['vmss_info'], 4, 79, capacity);

	#Sys info...
	write_str(window['system'], 1, 22, offer);
	write_str(window['system'], 2, 22, sku);
	cor=6;
	if (provisioningState == "Updating"): cor=7;
	write_str_color(window['system'], 4, 22, provisioningState, cor, 0);
	write_str(window['vmss_info'], 4, 14, dns);
	write_str(window['vmss_info'], 3, 14, ipaddr);

def update_vm_footer(window, cur_page, tot_pages):
	write_str(window['virtualmachines'], 31, 38, " Page: ");
	write_str(window['virtualmachines'], 31, 45, cur_page);
	write_str(window['virtualmachines'], 31, 47, "/");
	write_str(window['virtualmachines'], 31, 48, tot_pages);
	write_str(window['virtualmachines'], 31, 50, " ");

def fill_vm_details(window, instanceId, vmName, provisioningState):
	global vm_details; 
	write_str(window['vm'], 2, 17, instanceId);
	write_str(window['vm'], 3, 17, vmName);
	cor=7;
	if (provisioningState == "Succeeded"): cor=6;
	write_str_color(window['vm'], 4, 17, provisioningState, cor, 0);
	if (provisioningState == "Succeeded"):
		cdate = vm_details['statuses'][0]['time'];
		vmdate = cdate.split("T")
		vmtime = vmdate[1].split(".")
		write_str(window['vm'], 5, 17, vmdate[0]);
		write_str(window['vm'], 6, 17, vmtime[0]);
		cor=7;
		if (vm_details['statuses'][1]['displayStatus'] == "VM running"): cor=6;
		write_str_color(window['vm'], 7, 17, vm_details['statuses'][1]['displayStatus'], cor, 0);
		write_str(window['vm'], 8, 17, vm_details['platformUpdateDomain']);
		write_str(window['vm'], 9, 17, vm_details['platformFaultDomain']);
		write_str(window['vm'], 11, 12, vm_nic['value'][0]['name']);
		write_str(window['vm'], 12, 12, vm_nic['value'][0]['properties']['macAddress']);
		write_str(window['vm'], 13, 12, vm_nic['value'][0]['properties']['ipConfigurations'][0]['properties']['privateIPAddress']);
		write_str(window['vm'], 14, 12, vm_nic['value'][0]['properties']['ipConfigurations'][0]['properties']['primary']);
		if (vm_details['vmAgent']['statuses'][0]['message'] == "Guest Agent is running"): 
			cor=6;
			agentstatus = "Agent is running";
		write_str(window['vm'], 16, 12, vm_details['vmAgent']['vmAgentVersion']);
		write_str(window['vm'], 17, 12, vm_details['vmAgent']['statuses'][0]['displayStatus']);
		write_str_color(window['vm'], 18, 12, agentstatus, cor, 0);

def deselect_vm(window, panel, instanceId, counter):
	global vm_selected;

	vmsel = 0;
	if (vm_selected[1] == int(instanceId) and vm_selected[1] != vm_selected[0]):
		box(window[int(counter - 1)]);
	if (vm_selected[0] == int(instanceId) and vm_selected[1] != 999998 and vm_selected[0] != vm_selected[1]):
		vmsel = 1;
		show_panel(panel['vm']);
	if (vm_selected[0] == int(instanceId) and vm_selected[1] == 999998):
		vmsel = 0;
		vm_selected = [999999, 999999];
	return (vmsel);

def set_vmss_variables(vmssget, net):
	global vmsku, tier;

	name = vmssget['name']
	capacity = vmssget['sku']['capacity']
	location = vmssget['location'];
	tier = vmssget['sku']['tier']
	vmsku = vmssget['sku']['name']
	offer = vmssget['properties']['virtualMachineProfile']['storageProfile']['imageReference']['offer']
	sku = vmssget['properties']['virtualMachineProfile']['storageProfile']['imageReference']['sku']
	provisioningState = vmssget['properties']['provisioningState']
	dns = net['value'][0]['properties']['dnsSettings']['fqdn'];
	ipaddr = net['value'][0]['properties']['ipAddress'];
	return (name, capacity, location, offer, sku, provisioningState, dns, ipaddr);


# thread to loop around monitoring the VM Scale Set state and its VMs
# sleep between loops sets the update frequency
def get_vmss_properties(access_token, run_event, window_information, panel_information, window_continents, panel_continents):
	global vmssProperties, vmssVmProperties, countery, capacity, region, tier, vmsku, vm_selected, window_vm, panel_vm, instances_deployed, vm_details, vm_nic, page;

	ROOM = 5; DEPLOYED = 0;

	#VM's destination...
	destx = 22; desty = 4; XS =50; YS = 4; init_coords = (XS, YS);
	window_dc = 0;

	#Our window_information arrays...
	panel_vm = []; window_vm = [];

	#Our thread loop...
	while run_event.is_set():
		try:
			#Timestamp...
			ourtime = time.strftime("%H:%M:%S");
			write_str(window_information['status'], 1, 13, ourtime);

			#Clean Forms...
			clean_forms(window_information);

			#Get VMSS details
			vmssget = azurerm.get_vmss(access_token, subscription_id, rgname, vmssname);

			# Get public ip address for RG (First IP) - modify this if your RG has multiple ips
			net = azurerm.list_public_ips(access_token, subscription_id, rgname);

			#Fill the information...
			fill_vmss_info(window_information, vmssget, net);

			#Set VMSS variables...
			(name, capacity, location, offer, sku, provisioningState, dns, ipaddr) = set_vmss_variables(vmssget, net);

			#Set the current and old location...
			#Old
			old_location = region;
			if (old_location != ""):
				continent_old_location = get_continent_dc(old_location);

			#New
			region = location;
			continent_location = get_continent_dc(location);

			#Quota...
			quota = azurerm.get_compute_usage(access_token, subscription_id, location);
			fill_quota_info(window_information, quota);

			#Mark Datacenter where VMSS is deployed...
			if (old_location != ""):
				if (old_location != location):
					#Now switch the datacenter mark on map...
					new_window_dc = mark_vmss_dc(continent_old_location, window_continents[continent_old_location], old_location, window_continents[continent_location], location, window_dc);
					window_dc = new_window_dc;
			else:
				new_window_dc = mark_vmss_dc(continent_location, window_continents[continent_location], location, window_continents[continent_location], location, window_dc);
				window_dc = new_window_dc;

			#Our arrays...
			vmssProperties = [name, capacity, location, rgname, offer, sku, provisioningState, dns, ipaddr];
			vmssvms = azurerm.list_vmss_vms(access_token, subscription_id, rgname, vmssname);
			vmssVmProperties = [];

			#All VMs are created in the following coordinates...
			qtd = vmssvms['value'].__len__();
			factor = (vmssvms['value'].__len__() / 100);

			write_str(window_information['system'], 3, 22, qtd);

			step = qtd / 10;
			if (step < 1): step = 1;	

			#We take more time on our VM effect depending on how many VMs we are talking about...
			if (qtd < 20): ts = 0.01;
			elif (qtd < 60): ts = 0.003;
			elif (qtd < 100): ts = 0.0005;
			else: ts = 0;

			counter = 1; counter_page = 0; nr_pages = 1;

			snap_page = page;
			page_top = (snap_page * 100);
			page_base = ((snap_page - 1) * 100);

			#Loop each VM...
			for vm in vmssvms['value']:
				instanceId = vm['instanceId'];
				write_str(window_information['monitor'], 1, 30, instanceId);
				vmsel = 0;
				vmName = vm['name'];
				provisioningState = vm['properties']['provisioningState'];
				vmssVmProperties.append([instanceId, vmName, provisioningState]);
				if (counter > DEPLOYED):
					window_vm.append(DEPLOYED); panel_vm.append(DEPLOYED); instances_deployed.append(DEPLOYED);
					instances_deployed[DEPLOYED] = int(instanceId);
					#Prepare the place for the VM icon...
					if countery < 10:
						countery += 1;
					else:
						destx += 3; desty = 4; countery = 1;
					if (counter_page > 99):
						destx = 22; counter_page = 0; nr_pages += 1;
						cur_page = "%02d" % snap_page;
						tot_pages = "%02d" % nr_pages;
						update_vm_footer(window_information, cur_page, tot_pages);
					else:
						counter_page += 1;
					window_vm[DEPLOYED] = create_window(3, 5, init_coords[0], init_coords[1]);
					panel_vm[DEPLOYED] = new_panel(window_vm[DEPLOYED]);
					#Show only VM's that are on the visible window...
					if (page_top > DEPLOYED and DEPLOYED >= page_base):
						show_panel(panel_vm[DEPLOYED]);
					else:
						hide_panel(panel_vm[DEPLOYED]);
					box(window_vm[DEPLOYED]);
					#Creation of the VM icon, in this flow we never have a VM selected...
					draw_vm(int(instanceId), window_vm[DEPLOYED], provisioningState, vmsel);
					vm_animation(panel_vm[DEPLOYED], init_coords, destx, desty, 1, ts);
					desty += ROOM;
					DEPLOYED += 1;
				else:
					instances_deployed[counter - 1] = int(instanceId);
					#Remove the old mark...
					vmsel = deselect_vm(window_vm, panel_information, instanceId, counter);
					#Show only VM's that are on the visible window...
					if (page_top > (counter - 1) and (counter - 1) >= page_base):
						show_panel(panel_vm[counter -1]);
					else:
						hide_panel(panel_vm[counter -1]);
					#Creation of the VM icon...
					draw_vm(int(instanceId), window_vm[counter - 1], provisioningState, vmsel);
					#If a VM is selected, fill the details...
					if (vm_selected[0] == int(instanceId) and vm_selected[1] != 999998):
						vm_details = azurerm.get_vmss_vm_instance_view(access_token, subscription_id, rgname, vmssname, vm_selected[0]);
						vm_nic = azurerm.get_vmss_vm_nics(access_token, subscription_id, rgname, vmssname, vm_selected[0]);
						if (vm_details != "" and vm_nic != ""):
							fill_vm_details(window_information, instanceId, vmName, provisioningState);
				update_panels();
				doupdate();
				counter += 1;
				do_update_bar(window_information['status'], step, 0);
				step += step;
			#Last mile...
			write_str(window_information['monitor'], 1, 30, "Done.");
			do_update_bar(window_information['status'], step, 1);

			#Remove destroyed VMs...
			counter_page = 0;
			if (DEPLOYED >= counter):
				time.sleep(0.5);
				write_str_color(window_information['monitor'], 1, 30, "Removing deleted VM's", 7, 0);
				wrefresh(window_information['monitor']);
				time.sleep(1);
				clean_monitor_form(window_information);
	
			while (DEPLOYED >= counter):
				write_str(window_information['monitor'], 1, 30, DEPLOYED);
				lastvm = window_vm.__len__() - 1;	
				vm_coords = getbegyx(window_vm[lastvm]);
				vm_animation(panel_vm[lastvm], vm_coords, init_coords[0], init_coords[1], 0, ts);
				if (countery > 0):
					desty -= ROOM; countery -= 1;
				elif (destx > 22):
					destx -= 3; desty = 49; countery = 9;
				if (counter_page > 99):
					destx = 52;
					counter_page = 0;
					nr_pages -= 1;
					tot_pages = "%02d" % nr_pages;
					cur_page = "%02d" % page;
					update_vm_footer(window_information, cur_page, tot_pages);
				else:
					counter_page += 1;
				#Free up some memory...
				del_panel(panel_vm[lastvm]); delwin(window_vm[lastvm]);
				wobj = panel_vm[lastvm]; panel_vm.remove(wobj);
				wobj = window_vm[lastvm]; window_vm.remove(wobj);
				wobj = instances_deployed[lastvm]; instances_deployed.remove(wobj);
				DEPLOYED -= 1;
				update_panels();
				doupdate();
			write_str(window_information['monitor'], 1, 30, "Done.");
			ourtime = time.strftime("%H:%M:%S");
			do_update_bar(window_information['status'], step, 1);
			write_str(window_information['status'], 1, 13, ourtime);
			write_str_color(window_information['status'], 1, 22, "     OK     ", 6, 0);
			update_panels();
			doupdate();
			# sleep before each loop to avoid throttling...
			time.sleep(interval);
		except:
			logging.exception("ERROR:")
			write_str(window_information['error'], 1, 24, "Let's sleep for 30 seconds and try to refresh the dashboard again...");
			show_panel(panel_information['error']);
			update_panels();
			doupdate();
			## break out of loop when an error is encountered
			#break
			time.sleep(30);
			hide_panel(panel_information['error']);

def get_cmd(access_token, run_event, window_information, panel_information):
	global key, rgname, vmssname, vm_selected, quit;
	
	win_help = 0; win_log = 0;
	lock = threading.Lock()
	while (run_event.is_set() and quit == 0):
		with lock:
			key = getch();
		if (key == 58):
			curs_set(True);
			echo();
			#Clear the old command from our prompt line...
			wmove(window_information['cmd'], 1, 5); wclrtoeol(window_information['cmd']);
			create_prompt_form(window_information['cmd']);

			#Home...
			ourhome = platform.system();

			#Read the command...
			inputcommand = mvwgetstr(window_information['cmd'], 1, 5);
			if (ourhome == 'Windows'):
				command = inputcommand;
			else:
				command = inputcommand.decode('utf-8');

			curs_set(False);
			noecho();
			create_prompt_form(window_information['cmd']);

			cor=6;
			if (command == "help"):
				if (win_help):
					hide_panel(panel_information['help']);
					win_help = 0;
				else:
					show_panel(panel_information['help']);
					win_help = 1;
			elif (command == "log"):
				if (win_log):
					hide_panel(panel_information['log']);
					win_log = 0;
				else:
					show_panel(panel_information['log']);
					win_log = 1;
			elif (command == "quit" or command == 'exit'):
				quit = 1;
			elif (command == "deselect"):
				vm_selected[1] = 999998;
				hide_panel(panel_information['vm']);
			else:
				cmd_status = exec_cmd(window_information, access_token, capacity, command);
				if (cmd_status == 1): cor = 8;
				if (cmd_status == 2): cor = 4;
				if (cmd_status == 3): cor = 7;
				if (cmd_status == 4): cor = 3;
			write_str_color(window_information['cmd'], 1, 125, "E", cor, 1);
			update_panels();
			doupdate();

def vmss_monitor_thread(window_information, panel_information, window_continents, panel_continents):
	global access_token;

	run_event = threading.Event()
	run_event.set()

	# start a timer in order to refresh the access token in 10 minutes
	start_time = time.time();

	# get an access token for Azure authentication
	access_token = azurerm.get_access_token(str(tenant_id), str(app_id), str(app_secret));

	# logtail...
	thread = threading.Thread(target=tail_in_window, args=(logName, window_information['log'], panel_information['log'], run_event))
	thread.start()

	# start a VMSS monitoring thread
	vmss_thread = threading.Thread(target=get_vmss_properties, args=(access_token, run_event, window_information, panel_information, window_continents, panel_continents))
	vmss_thread.start()

	time.sleep(.2);

	# start a CMD Interpreter thread
	cmd_thread = threading.Thread(target=get_cmd, args=(access_token, run_event, window_information, panel_information))
	cmd_thread.start()

	try:
		while (quit == 0):
			time.sleep(.1);
		if (quit == 1):
			raise KeyboardInterrupt
	except KeyboardInterrupt:
		show_panel(panel_information['exit']);
		update_panels();
		doupdate();
		run_event.clear()
		vmss_thread.join()
		cmd_thread.join()
		wmove(window_information['exit'], 3, 5); wclrtoeol(window_information['exit']);
		box(window_information['exit']);
		write_str_color(window_information['exit'], 3, 6, "Console Update threads successfully closed.", 4, 1);
		update_panels();
		doupdate();
