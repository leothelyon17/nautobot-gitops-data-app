# NautobotCD GitOps Tool

The **NautobotCD GitOps Tool** is a Streamlit-based application designed to synchronize and deploy Nautobot objects from YAML files stored in a Git repository. It supports importing a wide variety of Nautobot object types—including roles, manufacturers, device types, locations, location types, statuses, prefixes, and devices (with interfaces, IP addresses, and optional `mgmt_only` flags)—directly into your Nautobot instance via its REST API.

## Features

- **Git-Based Synchronization:**
  - Clone a Git repository containing YAML files with definitions for Nautobot objects.
- **Compare & Validate:**
  - Check and compare the objects defined in the repository against those already in Nautobot before deployment.
- **Deploy Objects:**
  - Create independent objects (Roles, Manufacturers, Location Types, Statuses, Prefixes) first.
  - Then create dependent objects (Device Types, Locations, Devices).
  - Devices can include interfaces with IP addresses. If a device YAML includes a `primary_ip4` field, the corresponding IP address is assigned as the device’s primary IP.
  - Interfaces support an optional `mgmt_only` key.
- **Deletion Process:**
  - Delete objects in a safe order to maintain dependencies:
    - Devices → IP Addresses → Prefixes → Device Types & Locations → Roles, Manufacturers, Location Types, Statuses.
- **Real-Time Logging:**
  - View color-coded log messages as objects are imported or deleted.

## Requirements

- **Python 3.8+** (tested on Python 3.12)
- Nautobot instance (with API access)
- [GitPython](https://gitpython.readthedocs.io/en/stable/)
- [Streamlit](https://streamlit.io/)
- [streamlit-extras](https://pypi.org/project/streamlit-extras/)
- Requests, PyYAML, and other standard Python libraries

## Installation

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/yourusername/nautobot-gitops-tool.git
   cd nautobot-gitops-tool
