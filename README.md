#NautobotCD GitOps Tool

The NautobotCD GitOps Tool is a Streamlit-based application designed to synchronize and deploy Nautobot objects from YAML files stored in a Git repository. It supports importing a wide variety of Nautobot object types—including roles, manufacturers, device types, locations, location types, statuses, prefixes, and devices (with interfaces and IP addresses)—directly into your Nautobot instance via its REST API.

Features
Git-Based Synchronization:
Clone a Git repository containing YAML files with definitions for Nautobot objects.

Compare & Validate:
Check and compare the objects defined in the repository against what already exists in Nautobot before deployment.

Deploy Objects:
Create independent objects (e.g., roles, manufacturers, location types, statuses, and prefixes) first, then dependent objects (e.g., device types, locations, and devices).
Devices can include interfaces with IP addresses and an optional mgmt_only flag. If a device YAML includes a primary_ip4 field, the corresponding IP address is assigned as the device’s primary IP.

Deletion Process:
Delete objects in a safe order (devices → IP addresses → prefixes → device types & locations → independent objects) to ensure dependencies are handled correctly.

Real-Time Logging:
View log messages as objects are imported or deleted, with messages color-coded for clarity.

Requirements
Python 3.8+ (tested on Python 3.12)
Nautobot instance (with API access)
GitPython
Streamlit
Streamlit Extras (for stylable containers)
Requests, PyYAML, and other standard Python libraries
Installation
Clone the Repository:

bash
Copy
git clone https://github.com/yourusername/nautobot-gitops-tool.git
cd nautobot-gitops-tool
Create and Activate a Virtual Environment:

bash
Copy
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
Install Dependencies:

bash
Copy
pip install -r requirements.txt
Example requirements.txt:

nginx
Copy
streamlit
gitpython
requests
pyyaml
streamlit-extras
Configuration
Before running the app, ensure you have:

A valid Nautobot API token.
The URL to your Nautobot instance.
A Git repository containing your Nautobot YAML files (files should be organized in a designated subdirectory, for example, nautobot/objects).
The YAML files supported include:

manufacturers.yml
device_types.yml
roles.yml
locations.yml
location_types.yml
statuses.yml
prefixes.yml
devices.yml
The devices.yml file can include nested definitions for interfaces and IP addresses. For example:

yaml
Copy
- name: Test Device
  role: Know your role
  status: Active
  location: test location
  device-type: Test 123
  primary_ip4: 10.10.10.10/24
  interfaces:
    - name: mgmt0
      type: 1000base-t
      status: Active
      mgmt_only: true
      ip-address:
        - address: 10.10.10.10/24
          namespace: Global
          type: Host
          status: Active
Usage
Run the App:

bash
Copy
streamlit run app.py
Enter the Required Information:

Nautobot Token
Nautobot URL (e.g., http://your.nautobot.instance)
Git Repository URL (must end with .git)
Relative directory path within the repository (e.g., nautobot/objects)
Workflow:

Sync with Git:
Click this button to clone the repository, read the YAML files, and compare the objects with those in your Nautobot instance.

Deploy to Nautobot:
Once the comparison is complete, click this button to import (deploy) objects into Nautobot in the correct dependency order.
The tool will update device interfaces, assign IP addresses, and if a primary IP is specified, update the device accordingly.

Delete All Data:
Click the red button to delete all Nautobot objects in the proper order. This will first delete devices, then IP addresses, then prefixes, followed by device types, locations, and finally the remaining independent objects.

Deletion Order
When deleting, the tool ensures that dependent objects are removed first:

Devices
IP Addresses (to free up prefix dependencies)
Prefixes
Device Types & Locations
Roles, Manufacturers, Location Types, Statuses
Troubleshooting
400 Errors on Prefixes/IP Addresses:
Verify that your YAML definitions match Nautobot's API expectations. You might need to adjust field values (e.g., convert types to lowercase) or ensure that referenced objects (like namespaces and statuses) exist.

Lookup Inconsistencies:
If independent objects (like statuses or namespaces) are not available immediately for dependent object creation, consider adding a short delay (e.g., using time.sleep(2)) between phases.

Contributing
Contributions, bug fixes, and improvements are welcome! Please submit a pull request or open an issue for any changes you suggest.

License
This project is licensed under the MIT License
