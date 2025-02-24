from streamlit_extras.stylable_container import stylable_container
import streamlit as st
import yaml
import requests
import os
import tempfile
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import git  # Requires GitPython

# Initialize session state variables if not present.
if "check_done" not in st.session_state:
    st.session_state.check_done = False
if "delete_confirm" not in st.session_state:
    st.session_state.delete_confirm = False

# =============================
# NautobotClient Implementation
# =============================
class NautobotClient:
    def __init__(self, url: str, token: str | None = None, **kwargs):
        self.base_url = self._parse_url(url)
        self._token = token
        self.verify_ssl = kwargs.get("verify_ssl", False)
        self.retries = kwargs.get("retries", 3)
        self.timeout = kwargs.get("timeout", 10)
        self.proxies = kwargs.get("proxies", None)
        self._create_session()

    def _parse_url(self, url: str) -> str:
        parsed_url = urlparse(url)
        if not parsed_url.scheme:
            return f"http://{url}"
        return parsed_url.geturl()

    def _create_session(self):
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"
        self.session.headers["Accept"] = "application/json"
        self.session.headers["Authorization"] = f"Token {self._token}"
        if self.proxies:
            self.session.proxies.update(self.proxies)
        retry_method = Retry(total=self.retries, backoff_factor=1, 
                             status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry_method)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def http_call(self, method: str, url: str, data: dict | str | None = None,
                  json_data: dict | None = None, headers: dict | None = None,
                  verify: bool = False, params: dict | list[tuple] | None = None) -> dict:
        _request = requests.Request(
            method=method.upper(),
            url=self.base_url + url,
            data=data,
            json=json_data,
            headers=headers,
            params=params,
        )
        _request = self.session.prepare_request(_request)
        _response = self.session.send(request=_request, verify=verify, timeout=self.timeout)
        if _response.status_code not in (200, 201, 204):
            raise Exception(f"API call to {self.base_url + url} returned status code {_response.status_code}")
        if _response.status_code == 204:
            return {}
        return _response.json()

# =============================
# Simple Logging for Streamlit
# =============================
class Console:
    def log(self, message, style=None):
        if style == "error":
            st.error(message)
        elif style == "warning":
            st.warning(message)
        elif style == "success":
            st.success(message)
        else:
            st.info(message)

console = Console()

# =============================
# Compare and Check Files Function
# =============================
def check_and_compare_objects(nautobot_token: str, git_repo_url: str, subdirectory: str,
                              nautobot_url: str = "http://localhost:8080"):
    required_files = {
        "manufacturers.yml": {"endpoint": "/api/dcim/manufacturers/?limit=0", "object_type": "Manufacturers", "compare_key": "name"},
        "device_types.yml": {"endpoint": "/api/dcim/device-types/?limit=0", "object_type": "Device Types", "compare_key": "model"},
        "roles.yml": {"endpoint": "/api/extras/roles/?limit=0", "object_type": "Roles", "compare_key": "name"},
        "locations.yml": {"endpoint": "/api/dcim/locations/?limit=0", "object_type": "Locations", "compare_key": "name"},
        "location_types.yml": {"endpoint": "/api/dcim/location-types/?limit=0", "object_type": "Location Types", "compare_key": "name"},
        "statuses.yml": {"endpoint": "/api/extras/statuses/?limit=0", "object_type": "Statuses", "compare_key": "name"},
        "devices.yml": {"endpoint": "/api/dcim/devices/?limit=0", "object_type": "Devices", "compare_key": "name"},
    }
    found_files = {}
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            git.Repo.clone_from(git_repo_url, temp_dir)
        except Exception as e:
            console.log(f"Error cloning repository: {e}", style="error")
            return None
        for filename, info in required_files.items():
            file_path = os.path.join(temp_dir, subdirectory.strip("/"), filename)
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                try:
                    with open(file_path, "r") as f:
                        data = yaml.safe_load(f)
                        if isinstance(data, list):
                            found_files[filename] = data
                except Exception as e:
                    console.log(f"Error reading {filename}: {e}", style="error")
    st.markdown("### File Status:")
    for fname in required_files.keys():
        if fname in found_files:
            st.write(f"• {fname}")
        else:
            st.write(f"• {fname}: Not Found or Empty")
    nautobot_client = NautobotClient(url=nautobot_url, token=nautobot_token)
    compare_results = {}
    for filename, info in required_files.items():
        object_type = info["object_type"]
        compare_key = info["compare_key"]
        endpoint = info["endpoint"]
        if filename not in found_files:
            compare_results[object_type] = None
            continue
        git_list = found_files[filename]
        try:
            response = nautobot_client.http_call(method="get", url=endpoint)
            existing_objects = response.get("results", [])
        except Exception as e:
            console.log(f"Error retrieving {object_type} from Nautobot: {e}", style="error")
            compare_results[object_type] = None
            continue
        git_values = {obj.get(compare_key) for obj in git_list if isinstance(obj, dict) and obj.get(compare_key)}
        existing_values = {obj.get(compare_key) for obj in existing_objects if isinstance(obj, dict) and obj.get(compare_key)}
        diff = sorted(list(git_values - existing_values))
        compare_results[object_type] = diff if diff else None
    st.markdown("### Objects to be added to Nautobot:")
    for object_type in [info["object_type"] for info in required_files.values()]:
        st.markdown(f"**{object_type}:**")
        if compare_results.get(object_type):
            for val in compare_results[object_type]:
                st.success(val)
        else:
            st.info("None")
    st.session_state.check_done = True
    return compare_results

# =============================
# Sync All Objects Import Function from Git Repo
# =============================
def sync_all_objects_from_git(nautobot_token: str, git_repo_url: str, subdirectory: str,
                              nautobot_url: str = "http://localhost:8080"):
    # Process in dependency order.
    console.log(f"Cloning repository: {git_repo_url}", style="info")
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            git.Repo.clone_from(git_repo_url, temp_dir)
        except Exception as e:
            console.log(f"Error cloning repository: {e}", style="error")
            return
        # Independent objects.
        independent_files = {
            "roles.yml": {"endpoint": "/api/extras/roles/", "object_type": "Roles", "special": False, "compare_key": "name"},
            "manufacturers.yml": {"endpoint": "/api/dcim/manufacturers/", "object_type": "Manufacturers", "special": False, "compare_key": "name"},
            "location_types.yml": {"endpoint": "/api/dcim/location-types/", "object_type": "Location Types", "special": False, "compare_key": "name"},
            "statuses.yml": {"endpoint": "/api/extras/statuses/", "object_type": "Statuses", "special": False, "compare_key": "name"},
        }
        dependent_files = {
            "device_types.yml": {"endpoint": "/api/dcim/device-types/", "object_type": "Device Types", "special": "device_types", "compare_key": "model"},
            "locations.yml": {"endpoint": "/api/dcim/locations/", "object_type": "Locations", "special": "locations", "compare_key": "name"},
            "devices.yml": {"endpoint": "/api/dcim/devices/", "object_type": "Devices", "special": "devices", "compare_key": "name"},
        }
        nautobot_client = NautobotClient(url=nautobot_url, token=nautobot_token)
        # Process independent objects.
        for filename, info in independent_files.items():
            file_path = os.path.join(temp_dir, subdirectory.strip("/"), filename)
            if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                console.log(f"{filename} not found or empty; skipping.", style="warning")
                continue
            try:
                with open(file_path, "r") as f:
                    data_list = yaml.safe_load(f)
            except Exception as e:
                console.log(f"Error reading {filename}: {e}", style="error")
                continue
            if not isinstance(data_list, list):
                console.log(f"{filename} does not contain a list; skipping.", style="warning")
                continue
            try:
                existing_resp = nautobot_client.http_call(method="get", url=info["endpoint"] + "?limit=0")
                existing_objs = existing_resp.get("results", [])
            except Exception as e:
                console.log(f"Error fetching existing {info['object_type']} for duplicate check: {e}", style="error")
                existing_objs = []
            existing_set = {obj.get(info["compare_key"]) for obj in existing_objs if obj.get(info["compare_key"])}
            console.log(f"Processing {len(data_list)} object(s) in {filename}.", style="info")
            for obj in data_list:
                if not isinstance(obj, dict) or not obj.get(info["compare_key"]):
                    continue
                if obj.get(info["compare_key"]) in existing_set:
                    continue
                payload = obj
                try:
                    result = nautobot_client.http_call(method="post", url=info["endpoint"], json_data=payload)
                    display_val = result.get("display") or payload.get("name")
                    console.log(f"Imported {info['object_type'][:-1]}: {display_val}", style="success")
                except Exception as e:
                    console.log(f"Error importing {info['object_type'][:-1]} '{payload.get(info['compare_key'])}': {e}", style="error")
        # Refresh independent lookups.
        roles_lookup = {}
        try:
            response = nautobot_client.http_call(method="get", url="/api/extras/roles/?limit=0")
            for r in response.get("results", []):
                if r.get("name"):
                    roles_lookup[r["name"]] = r.get("id")
        except Exception as e:
            console.log(f"Error retrieving roles for lookup: {e}", style="error")
        manufacturers_lookup = {}
        try:
            response = nautobot_client.http_call(method="get", url="/api/dcim/manufacturers/?limit=0")
            for m in response.get("results", []):
                if m.get("name"):
                    manufacturers_lookup[m["name"]] = m.get("id")
        except Exception as e:
            console.log(f"Error retrieving manufacturers for lookup: {e}", style="error")
        location_types_lookup = {}
        try:
            response = nautobot_client.http_call(method="get", url="/api/dcim/location-types/?limit=0")
            for lt in response.get("results", []):
                if lt.get("name"):
                    location_types_lookup[lt["name"]] = lt.get("id")
        except Exception as e:
            console.log(f"Error retrieving location types for lookup: {e}", style="error")
        statuses_lookup = {}
        try:
            response = nautobot_client.http_call(method="get", url="/api/extras/statuses/?limit=0")
            for s in response.get("results", []):
                if s.get("name"):
                    statuses_lookup[s["name"]] = s.get("id")
        except Exception as e:
            console.log(f"Error retrieving statuses for lookup: {e}", style="error")
        # Process dependent objects.
        # Device Types
        for filename, info in dependent_files.items():
            if filename != "device_types.yml":
                continue
            file_path = os.path.join(temp_dir, subdirectory.strip("/"), filename)
            if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                console.log(f"{filename} not found or empty; skipping.", style="warning")
                continue
            try:
                with open(file_path, "r") as f:
                    data_list = yaml.safe_load(f)
            except Exception as e:
                console.log(f"Error reading {filename}: {e}", style="error")
                continue
            if not isinstance(data_list, list):
                console.log(f"{filename} does not contain a list; skipping.", style="warning")
                continue
            try:
                existing_resp = nautobot_client.http_call(method="get", url=info["endpoint"] + "?limit=0")
                existing_objs = existing_resp.get("results", [])
            except Exception as e:
                console.log(f"Error fetching existing {info['object_type']} for duplicate check: {e}", style="error")
                existing_objs = []
            existing_set = {obj.get(info["compare_key"]) for obj in existing_objs if obj.get(info["compare_key"])}
            console.log(f"Processing {len(data_list)} object(s) in {filename}.", style="info")
            for obj in data_list:
                if not isinstance(obj, dict) or not obj.get(info["compare_key"]):
                    continue
                if obj.get(info["compare_key"]) in existing_set:
                    continue
                if info["special"] == "device_types":
                    if not all(k in obj for k in ["model", "manufacturer", "u_height"]):
                        console.log("Skipping invalid device type entry; must include 'model', 'manufacturer', and 'u_height'.", style="warning")
                        continue
                    manufacturer_name = obj.get("manufacturer")
                    manufacturer_id = manufacturers_lookup.get(manufacturer_name)
                    if not manufacturer_id:
                        console.log(f"Manufacturer '{manufacturer_name}' not found; skipping device type {obj.get('model')}.", style="error")
                        continue
                    payload = {"model": obj.get("model"), "manufacturer": {"id": manufacturer_id}, "height": obj.get("u_height")}
                else:
                    payload = obj
                try:
                    result = nautobot_client.http_call(method="post", url=info["endpoint"], json_data=payload)
                    display_val = result.get("display") or payload.get("model")
                    console.log(f"Imported Device Type: {display_val}", style="success")
                except Exception as e:
                    console.log(f"Error importing device type '{payload.get('model')}': {e}", style="error")
        # Refresh device types lookup.
        device_types_lookup = {}
        try:
            response = nautobot_client.http_call(method="get", url="/api/dcim/device-types/?limit=0")
            for dt in response.get("results", []):
                if dt.get("model"):
                    device_types_lookup[dt["model"]] = dt.get("id")
        except Exception as e:
            console.log(f"Error retrieving device types for lookup: {e}", style="error")
        # Locations
        for filename, info in dependent_files.items():
            if filename != "locations.yml":
                continue
            file_path = os.path.join(temp_dir, subdirectory.strip("/"), filename)
            if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                console.log(f"{filename} not found or empty; skipping.", style="warning")
                continue
            try:
                with open(file_path, "r") as f:
                    data_list = yaml.safe_load(f)
            except Exception as e:
                console.log(f"Error reading {filename}: {e}", style="error")
                continue
            if not isinstance(data_list, list):
                console.log(f"{filename} does not contain a list; skipping.", style="warning")
                continue
            try:
                existing_resp = nautobot_client.http_call(method="get", url=info["endpoint"] + "?limit=0")
                existing_objs = existing_resp.get("results", [])
            except Exception as e:
                console.log(f"Error fetching existing {info['object_type']} for duplicate check: {e}", style="error")
                existing_objs = []
            existing_set = {obj.get(info["compare_key"]) for obj in existing_objs if obj.get(info["compare_key"])}
            console.log(f"Processing {len(data_list)} object(s) in {filename}.", style="info")
            for obj in data_list:
                if not isinstance(obj, dict) or not obj.get(info["compare_key"]):
                    continue
                if obj.get(info["compare_key"]) in existing_set:
                    continue
                if info["special"] == "locations":
                    if not all(k in obj for k in ["name", "location_type"]):
                        console.log("Skipping invalid location entry; must include 'name' and 'location_type'.", style="warning")
                        continue
                    location_type_name = obj.get("location_type")
                    location_type_id = location_types_lookup.get(location_type_name)
                    if not location_type_id:
                        console.log(f"Location type '{location_type_name}' not found; skipping location {obj.get('name')}.", style="error")
                        continue
                    payload = obj.copy()
                    payload["location_type"] = {"id": location_type_id}
                else:
                    payload = obj
                try:
                    result = nautobot_client.http_call(method="post", url=info["endpoint"], json_data=payload)
                    display_val = result.get("display") or payload.get("name")
                    console.log(f"Imported Location: {display_val}", style="success")
                except Exception as e:
                    console.log(f"Error importing location '{payload.get('name')}': {e}", style="error")
        # Refresh locations lookup.
        locations_lookup = {}
        try:
            response = nautobot_client.http_call(method="get", url="/api/dcim/locations/?limit=0")
            for l in response.get("results", []):
                if l.get("name"):
                    locations_lookup[l["name"]] = l.get("id")
        except Exception as e:
            console.log(f"Error retrieving locations for lookup: {e}", style="error")
        # Devices
        for filename, info in dependent_files.items():
            if filename != "devices.yml":
                continue
            file_path = os.path.join(temp_dir, subdirectory.strip("/"), filename)
            if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                console.log(f"{filename} not found or empty; skipping.", style="warning")
                continue
            try:
                with open(file_path, "r") as f:
                    data_list = yaml.safe_load(f)
            except Exception as e:
                console.log(f"Error reading {filename}: {e}", style="error")
                continue
            if not isinstance(data_list, list):
                console.log(f"{filename} does not contain a list; skipping.", style="warning")
                continue
            try:
                existing_resp = nautobot_client.http_call(method="get", url=info["endpoint"] + "?limit=0")
                existing_objs = existing_resp.get("results", [])
            except Exception as e:
                console.log(f"Error fetching existing {info['object_type']} for duplicate check: {e}", style="error")
                existing_objs = []
            existing_set = {obj.get(info["compare_key"]) for obj in existing_objs if obj.get(info["compare_key"])}
            console.log(f"Processing {len(data_list)} object(s) in {filename}.", style="info")
            for obj in data_list:
                if not isinstance(obj, dict) or not obj.get(info["compare_key"]):
                    continue
                if obj.get(info["compare_key"]) in existing_set:
                    continue
                if info["special"] == "devices":
                    if not all(k in obj for k in ["name", "role", "status", "location", "device-type"]):
                        console.log("Skipping invalid device entry; must include 'name', 'role', 'status', 'location', and 'device-type'.", style="warning")
                        continue
                    role_id = roles_lookup.get(obj.get("role"))
                    status_id = statuses_lookup.get(obj.get("status"))
                    location_id = locations_lookup.get(obj.get("location"))
                    device_type_id = device_types_lookup.get(obj.get("device-type"))
                    if not role_id:
                        console.log(f"Device role '{obj.get('role')}' not found; skipping device {obj.get('name')}.", style="error")
                        continue
                    if not status_id:
                        console.log(f"Status '{obj.get('status')}' not found; skipping device {obj.get('name')}.", style="error")
                        continue
                    if not location_id:
                        console.log(f"Location '{obj.get('location')}' not found; skipping device {obj.get('name')}.", style="error")
                        continue
                    if not device_type_id:
                        console.log(f"Device type '{obj.get('device-type')}' not found; skipping device {obj.get('name')}.", style="error")
                        continue
                    payload = {
                        "name": obj.get("name"),
                        "role": {"id": role_id},
                        "status": {"id": status_id},
                        "location": {"id": location_id},
                        "device_type": {"id": device_type_id},
                    }
                else:
                    payload = obj
                try:
                    result = nautobot_client.http_call(method="post", url=info["endpoint"], json_data=payload)
                    display_val = result.get("display") or payload.get("name")
                    console.log(f"Imported Device: {display_val}", style="success")
                except Exception as e:
                    console.log(f"Error importing device '{payload.get('name')}': {e}", style="error")
    console.log("Sync process completed.", style="warning")

# =============================
# Delete All Data Function (Big Red Button)
# =============================
def delete_all_data(nautobot_token: str, nautobot_url: str = "http://localhost:8080"):
    nautobot_client = NautobotClient(url=nautobot_url, token=nautobot_token)
    deletion_order = [
        {"endpoint": "/api/dcim/devices/", "object_type": "Devices"},
        {"endpoint": "/api/dcim/device-types/", "object_type": "Device Types"},
        {"endpoint": "/api/dcim/locations/", "object_type": "Locations"},
        {"endpoint": "/api/extras/roles/", "object_type": "Roles"},
        {"endpoint": "/api/dcim/manufacturers/", "object_type": "Manufacturers"},
        {"endpoint": "/api/dcim/location-types/", "object_type": "Location Types"},
        {"endpoint": "/api/extras/statuses/", "object_type": "Statuses"},
    ]
    for item in deletion_order:
        ep = item["endpoint"]
        obj_type = item["object_type"]
        try:
            response = nautobot_client.http_call(method="get", url=ep + "?limit=0")
            objects = response.get("results", [])
        except Exception as e:
            console.log(f"Error retrieving {obj_type} for deletion: {e}", style="error")
            continue
        for obj in objects:
            obj_id = obj.get("id")
            name = obj.get("name") or obj.get("model")
            if obj_id:
                delete_url = f"{ep}{obj_id}/"
                try:
                    nautobot_client.http_call(method="delete", url=delete_url)
                    console.log(f"Deleted {obj_type[:-1]}: {name}", style="success")
                except Exception as e:
                    console.log(f"Error deleting {obj_type[:-1]} '{name}': {e}", style="error")
    console.log("Deletion process completed.", style="warning")

# =============================
# Streamlit App UI
# =============================
st.title("Nautobot Objects Importer, Comparator, and Deleter")

st.markdown(
    """
Provide your Nautobot credentials, a Git repository URL (ending with `.git`), and the relative directory path within that repository 
where your Nautobot YAML object files are located.

- **Compare and Check Files:** Verify the presence of required YAML files and compare the objects with those already in Nautobot.
- **Sync Nautobot Data:** Import all objects in dependency order:
    1. Independent objects: Roles, Manufacturers, Location Types, Statuses.
    2. Dependent objects: Device Types (dependent on Manufacturers), Locations (dependent on Location Types), then Devices (dependent on Role, Status, Location, and Device Type).
- **Delete All Data:** Permanently delete all objects from Nautobot in the following order:
    Devices → Device Types & Locations → Roles, Manufacturers, Location Types, Statuses.
"""
)

nautobot_token = st.text_input("Enter Nautobot Token")
nautobot_url = st.text_input("Enter Nautobot URL", value="http://localhost:8080")
git_repo_url = st.text_input("Enter Git Repository URL (ending with .git)")
subdirectory = st.text_input("Enter directory path within the repo (e.g., 'nautobot/objects')")

if st.button("Compare and Check Files"):
    if not nautobot_token:
        st.error("Please enter your Nautobot Token.")
    elif not git_repo_url:
        st.error("Please enter the Git repository URL.")
    elif not subdirectory:
        st.error("Please enter the directory path.")
    else:
        st.info("Checking repository for required YAML files and comparing objects...")
        check_and_compare_objects(nautobot_token, git_repo_url, subdirectory, nautobot_url)

if st.session_state.get("check_done", False):
    with stylable_container("green", css_styles="""
        button {
            background-color: #00FF00;
            color: black;
            font-weight: bold;
        }
    """):
        if st.button("Sync Nautobot Data"):
            if not nautobot_token:
                st.error("Please enter your Nautobot Token.")
            elif not git_repo_url:
                st.error("Please enter the Git repository URL.")
            elif not subdirectory:
                st.error("Please enter the directory path containing your YAML files.")
            else:
                st.info("Starting sync of all objects to Nautobot in dependency order...")
                try:
                    sync_all_objects_from_git(nautobot_token, git_repo_url, subdirectory, nautobot_url)
                    st.markdown('<div style="background-color: yellow; padding: 5px;">Nautobot data sync process completed (check logs above).</div>', unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"An error occurred during sync: {e}")
else:
    st.info("Please run 'Compare and Check Files' first to enable syncing.")

with stylable_container("red", css_styles="""
    button {
        background-color: #FF0000;
        color: white;
        font-weight: bold;
    }
"""):
    if st.button("Delete All Data"):
        if not nautobot_token:
            st.error("Please enter your Nautobot Token.")
        else:
            st.error("WARNING: This will permanently delete all specified Nautobot objects. Proceed with caution!")
            st.session_state.delete_confirm = True

if st.session_state.get("delete_confirm", False):
    if st.button("CONFIRM DELETE ALL DATA"):
        try:
            delete_all_data(nautobot_token, nautobot_url)
            st.markdown('<div style="background-color: yellow; padding: 5px;">All data deleted successfully.</div>', unsafe_allow_html=True)
            st.session_state.delete_confirm = False
        except Exception as e:
            st.error(f"An error occurred during deletion: {e}")





