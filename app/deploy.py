import os
import tempfile
import git
import yaml
from nautobot_client import NautobotClient
from logger import console

def sync_all_objects_from_git(nautobot_token: str, git_repo_url: str, subdirectory: str,
                              nautobot_url: str = "http://localhost:8080", username: str = None, token: str = None):
    console.log(f"Cloning repository: {git_repo_url}", style="info")
    # If authentication credentials are provided, insert them into the URL.
    if username and token:
        if git_repo_url.startswith("https://"):
            git_repo_url = git_repo_url.replace("https://", f"https://{username}:{token}@")
        elif git_repo_url.startswith("http://"):
            git_repo_url = git_repo_url.replace("http://", f"http://{username}:{token}@")
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            git.Repo.clone_from(git_repo_url, temp_dir)
        except Exception as e:
            console.log(f"Error cloning repository: {e}", style="error")
            return
        # Define independent files.
        independent_files = {
            "roles.yml": {"endpoint": "/api/extras/roles/", "object_type": "Roles", "special": False, "compare_key": "name"},
            "manufacturers.yml": {"endpoint": "/api/dcim/manufacturers/", "object_type": "Manufacturers", "special": False, "compare_key": "name"},
            "location_types.yml": {"endpoint": "/api/dcim/location-types/", "object_type": "Location Types", "special": False, "compare_key": "name"},
            "statuses.yml": {"endpoint": "/api/extras/statuses/", "object_type": "Statuses", "special": False, "compare_key": "name"},
            "prefixes.yml": {"endpoint": "/api/ipam/prefixes/", "object_type": "Prefixes", "special": "prefixes", "compare_key": "prefix"},
        }
        # Define dependent files.
        dependent_files = {
            "device_types.yml": {"endpoint": "/api/dcim/device-types/", "object_type": "Device Types", "special": "device_types", "compare_key": "model"},
            "locations.yml": {"endpoint": "/api/dcim/locations/", "object_type": "Locations", "special": "locations", "compare_key": "name"},
            "devices.yml": {"endpoint": "/api/dcim/devices/", "object_type": "Devices", "special": "devices", "compare_key": "name"},
        }
        nautobot_client = NautobotClient(url=nautobot_url, token=nautobot_token)
        # Pre-fetch IPAM namespaces.
        namespaces_lookup = {}
        try:
            response = nautobot_client.http_call(method="get", url="/api/ipam/namespaces/?limit=0")
            for ns in response.get("results", []):
                if ns.get("name"):
                    namespaces_lookup[ns["name"]] = ns.get("id")
        except Exception as e:
            console.log(f"Error retrieving namespaces: {e}", style="error")
        repo_dir = os.path.join(temp_dir, subdirectory.strip("/"))
        # Process independent objects.
        for filename, info in independent_files.items():
            file_path = os.path.join(repo_dir, filename)
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
                console.log(f"Error fetching existing {info['object_type']}: {e}", style="error")
                existing_objs = []
            existing_set = {obj.get(info["compare_key"]) for obj in existing_objs if obj.get(info["compare_key"])}
            console.log(f"Processing {len(data_list)} object(s) in {filename}.", style="info")
            for obj in data_list:
                if not isinstance(obj, dict) or not obj.get(info["compare_key"]):
                    continue
                if obj.get(info["compare_key"]) in existing_set:
                    continue
                if info.get("special") == "prefixes":
                    if not all(k in obj for k in ["prefix", "namespace", "type", "status"]):
                        console.log("Skipping invalid prefix entry.", style="warning")
                        continue
                    ns_name = obj.get("namespace")
                    ns_id = namespaces_lookup.get(ns_name)
                    if not ns_id:
                        console.log(f"Namespace '{ns_name}' not found; skipping prefix {obj.get('prefix')}.", style="warning")
                        continue
                    prefix_type = obj.get("type").lower() if obj.get("type") else None
                    try:
                        resp_status = nautobot_client.http_call(method="get", url="/api/extras/statuses/?limit=0")
                        statuses = resp_status.get("results", [])
                        statuses_lookup = {s.get("name"): s.get("id") for s in statuses if s.get("name")}
                        status_id = statuses_lookup.get(obj.get("status"))
                    except Exception as e:
                        console.log(f"Error retrieving statuses: {e}", style="error")
                        status_id = None
                    if not status_id:
                        console.log(f"Status '{obj.get('status')}' not found; skipping prefix {obj.get('prefix')}.", style="warning")
                        continue
                    payload = {"prefix": obj.get("prefix"), "namespace": {"id": ns_id}, "type": prefix_type, "status": {"id": status_id}}
                else:
                    payload = obj
                try:
                    result = nautobot_client.http_call(method="post", url=info["endpoint"], json_data=payload)
                    label = "Prefix" if info["object_type"] == "Prefixes" else info["object_type"][:-1]
                    display_val = result.get("display") or payload.get("name") or payload.get("prefix")
                    console.log(f"Imported {label}: {display_val}", style="success")
                except Exception as e:
                    console.log(f"Error importing {info['object_type'][:-1]}: {e}", style="error")
        # Refresh independent lookups.
        try:
            response = nautobot_client.http_call(method="get", url="/api/extras/roles/?limit=0")
            roles_lookup = {r.get("name"): r.get("id") for r in response.get("results", []) if r.get("name")}
        except Exception as e:
            console.log(f"Error retrieving roles: {e}", style="error")
            roles_lookup = {}
        try:
            response = nautobot_client.http_call(method="get", url="/api/dcim/manufacturers/?limit=0")
            manufacturers_lookup = {m.get("name"): m.get("id") for m in response.get("results", []) if m.get("name")}
        except Exception as e:
            console.log(f"Error retrieving manufacturers: {e}", style="error")
            manufacturers_lookup = {}
        try:
            response = nautobot_client.http_call(method="get", url="/api/dcim/location-types/?limit=0")
            location_types_lookup = {lt.get("name"): lt.get("id") for lt in response.get("results", []) if lt.get("name")}
        except Exception as e:
            console.log(f"Error retrieving location types: {e}", style="error")
            location_types_lookup = {}
        try:
            response = nautobot_client.http_call(method="get", url="/api/extras/statuses/?limit=0")
            statuses_lookup = {s.get("name"): s.get("id") for s in response.get("results", []) if s.get("name")}
        except Exception as e:
            console.log(f"Error retrieving statuses: {e}", style="error")
            statuses_lookup = {}
        # Process dependent objects: Device Types.
        for filename, info in dependent_files.items():
            if filename != "device_types.yml":
                continue
            file_path = os.path.join(repo_dir, filename)
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
                console.log(f"Error fetching existing device types: {e}", style="error")
                existing_objs = []
            existing_set = {obj.get(info["compare_key"]) for obj in existing_objs if obj.get(info["compare_key"])}
            console.log(f"Processing {len(data_list)} object(s) in {filename}.", style="info")
            for obj in data_list:
                if not isinstance(obj, dict) or not obj.get(info["compare_key"]):
                    continue
                if obj.get(info["compare_key"]) in existing_set:
                    continue
                if info.get("special") == "device_types":
                    if not all(k in obj for k in ["model", "manufacturer", "u_height"]):
                        console.log("Skipping invalid device type entry.", style="warning")
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
                    console.log(f"Error importing device type: {e}", style="error")
        # Refresh device types lookup.
        try:
            response = nautobot_client.http_call(method="get", url="/api/dcim/device-types/?limit=0")
            device_types_lookup = {dt.get("model"): dt.get("id") for dt in response.get("results", []) if dt.get("model")}
        except Exception as e:
            console.log(f"Error retrieving device types: {e}", style="error")
            device_types_lookup = {}
        
        # ----- Process Interface Templates -----
        process_interface_templates(nautobot_client, repo_dir, "interface_templates.yml", device_types_lookup)
        
        # Process dependent objects: Locations.
        for filename, info in dependent_files.items():
            if filename != "locations.yml":
                continue
            file_path = os.path.join(repo_dir, filename)
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
                console.log(f"Error fetching existing locations: {e}", style="error")
                existing_objs = []
            existing_set = {obj.get(info["compare_key"]) for obj in existing_objs if obj.get(info["compare_key"])}
            console.log(f"Processing {len(data_list)} object(s) in {filename}.", style="info")
            for obj in data_list:
                if not isinstance(obj, dict) or not obj.get(info["compare_key"]):
                    continue
                if obj.get(info["compare_key"]) in existing_set:
                    continue
                if info.get("special") == "locations":
                    if not all(k in obj for k in ["name", "location_type"]):
                        console.log("Skipping invalid location entry.", style="warning")
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
                    console.log(f"Error importing location: {e}", style="error")
        # Refresh locations lookup.
        try:
            response = nautobot_client.http_call(method="get", url="/api/dcim/locations/?limit=0")
            locations_lookup = {l.get("name"): l.get("id") for l in response.get("results", []) if l.get("name")}
        except Exception as e:
            console.log(f"Error retrieving locations: {e}", style="error")
            locations_lookup = {}
        # Process dependent objects: Devices.
        for filename, info in dependent_files.items():
            if filename != "devices.yml":
                continue
            file_path = os.path.join(repo_dir, filename)
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
                existing_devices = {obj.get(info["compare_key"]): obj for obj in existing_objs if obj.get(info["compare_key"])}
            except Exception as e:
                console.log(f"Error fetching existing devices: {e}", style="error")
                existing_devices = {}
            console.log(f"Processing {len(data_list)} device(s) in {filename}.", style="info")
            for obj in data_list:
                if not isinstance(obj, dict) or not obj.get(info["compare_key"]):
                    continue
                device_name = obj.get("name")
                primary_ip_address = obj.get("primary_ip4")
                primary_ip_id = None
                if device_name in existing_devices:
                    update_payload = {}
                    new_role = roles_lookup.get(obj.get("role"))
                    if new_role and existing_devices[device_name].get("role", {}).get("id") != new_role:
                        update_payload["role"] = {"id": new_role}
                    new_status = statuses_lookup.get(obj.get("status"))
                    if new_status and existing_devices[device_name].get("status", {}).get("id") != new_status:
                        update_payload["status"] = {"id": new_status}
                    new_location = locations_lookup.get(obj.get("location"))
                    if new_location and existing_devices[device_name].get("location", {}).get("id") != new_location:
                        update_payload["location"] = {"id": new_location}
                    new_device_type = device_types_lookup.get(obj.get("device-type"))
                    if new_device_type and existing_devices[device_name].get("device_type", {}).get("id") != new_device_type:
                        update_payload["device_type"] = {"id": new_device_type}
                    if update_payload:
                        try:
                            patch_url = f"/api/dcim/devices/{existing_devices[device_name].get('id')}/"
                            _ = nautobot_client.http_call(method="patch", url=patch_url, json_data=update_payload)
                            console.log(f"Updated Device: {device_name}", style="success")
                        except Exception as e:
                            console.log(f"Error updating device '{device_name}': {e}", style="error")
                    else:
                        console.log(f"Device {device_name} is already up-to-date", style="info")
                    device_id = existing_devices[device_name].get("id")
                else:
                    payload = {
                        "name": obj.get("name"),
                        "role": {"id": roles_lookup.get(obj.get("role"))},
                        "status": {"id": statuses_lookup.get(obj.get("status"))},
                        "location": {"id": locations_lookup.get(obj.get("location"))},
                        "device_type": {"id": device_types_lookup.get(obj.get("device-type"))},
                    }
                    try:
                        result = nautobot_client.http_call(method="post", url=info["endpoint"], json_data=payload)
                        console.log(f"Imported Device: {result.get('display') or payload.get('name')}", style="success")
                        device_id = result.get("id")
                    except Exception as e:
                        console.log(f"Error importing device '{payload.get('name')}': {e}", style="error")
                        continue
                try:
                    existing_ifaces_response = nautobot_client.http_call(method="get", url=f"/api/dcim/interfaces/?device={device_id}")
                    existing_ifaces = {iface["name"]: iface for iface in existing_ifaces_response.get("results", []) if "name" in iface}
                except Exception as e:
                    existing_ifaces = {}
                interfaces = obj.get("interfaces") if isinstance(obj.get("interfaces"), list) else []
                for interface in interfaces:
                    if not isinstance(interface, dict) or "name" not in interface or "status" not in interface:
                        console.log("Skipping invalid interface entry.", style="warning")
                        continue
                    iface_name = interface.get("name")
                    iface_status_id = statuses_lookup.get(interface["status"])
                    if not iface_status_id:
                        console.log(f"Interface status '{interface['status']}' not found; skipping interface {iface_name}.", style="error")
                        continue
                    payload_iface = {
                        "device": {"id": device_id},
                        "name": iface_name,
                        "type": interface.get("type"),
                        "status": {"id": iface_status_id},
                    }
                    if interface.get("mgmt_only") is True:
                        payload_iface["mgmt_only"] = True
                    if iface_name in existing_ifaces:
                        existing_iface = existing_ifaces[iface_name]
                        needs_update = False
                        # Compare only the interface type value in lowercase.
                        existing_type = existing_iface.get("type")
                        if isinstance(existing_type, dict):
                            existing_type_value = existing_type.get("value", "").lower()
                        else:
                            existing_type_value = str(existing_type).lower() if existing_type else ""
                        payload_type_value = str(payload_iface.get("type")).lower() if payload_iface.get("type") else ""
                        if existing_type_value != payload_type_value:
                            needs_update = True
                        if existing_iface.get("status", {}).get("id") != payload_iface.get("status", {}).get("id"):
                            needs_update = True
                        if "mgmt_only" in payload_iface and existing_iface.get("mgmt_only") != payload_iface.get("mgmt_only"):
                            needs_update = True
                        if needs_update:
                            try:
                                patch_url = f"/api/dcim/interfaces/{existing_iface.get('id')}/"
                                iface_result = nautobot_client.http_call(method="patch", url=patch_url, json_data=payload_iface)
                                console.log(f"Updated Interface: {iface_result.get('display') or iface_name} on device {device_name}", style="success")
                            except Exception as e:
                                console.log(f"Error updating interface '{iface_name}': {e}", style="error")
                                continue
                        else:
                            iface_result = existing_iface
                    else:
                        try:
                            iface_result = nautobot_client.http_call(method="post", url="/api/dcim/interfaces/", json_data=payload_iface)
                            console.log(f"Imported Interface: {iface_result.get('display') or iface_name} on device {device_name}", style="success")
                        except Exception as e:
                            console.log(f"Error importing interface '{iface_name}': {e}", style="error")
                            continue
                    # Process IP address mappings.
                    try:
                        existing_ips_response = nautobot_client.http_call(method="get", url=f"/api/ipam/ip-addresses/?interface={iface_result.get('id')}")
                        existing_ips = {ip["address"]: ip for ip in existing_ips_response.get("results", []) if "address" in ip}
                    except Exception:
                        existing_ips = {}
                    if "ip-address" in interface and isinstance(interface["ip-address"], list):
                        for ip_obj in interface["ip-address"]:
                            if not isinstance(ip_obj, dict) or not ip_obj.get("address"):
                                console.log("Skipping invalid ip-address entry.", style="warning")
                                continue
                            if not all(k in ip_obj for k in ["address", "namespace", "type", "status"]):
                                console.log("Skipping invalid ip-address entry.", style="warning")
                                continue
                            ip_address = ip_obj.get("address")
                            if ip_address in existing_ips:
                                console.log(f"IP Address {ip_address} already exists on interface {iface_result.get('id')} for device {device_name}; skipping mapping.", style="info")
                                if primary_ip_address and ip_address == primary_ip_address:
                                    primary_ip_id = existing_ips[ip_address].get("id")
                                continue
                            try:
                                mapping_search = nautobot_client.http_call(
                                    method="get",
                                    url=f"/api/ipam/ip-address-to-interface/?interface={iface_result.get('id')}&ip_address={ip_address}"
                                )
                                if mapping_search.get("results"):
                                    console.log(f"Mapping for IP {ip_address} already exists on interface {iface_result.get('id')}; skipping mapping.", style="info")
                                    if primary_ip_address and ip_address == primary_ip_address:
                                        primary_ip_id = mapping_search["results"][0].get("ip_address", {}).get("id")
                                    continue
                            except Exception:
                                pass
                            try:
                                ip_search_response = nautobot_client.http_call(method="get", url=f"/api/ipam/ip-addresses/?address={ip_address}")
                                ip_search_results = ip_search_response.get("results", [])
                            except Exception:
                                ip_search_results = []
                            if ip_search_results:
                                ip_id = ip_search_results[0].get("id")
                                mapping_payload = {"ip_address": {"id": ip_id}, "interface": {"id": iface_result.get("id")}}
                                try:
                                    mapping_check = nautobot_client.http_call(
                                        method="get",
                                        url=f"/api/ipam/ip-address-to-interface/?interface={iface_result.get('id')}&ip_address={ip_id}"
                                    )
                                    if mapping_check.get("results"):
                                        if primary_ip_address and ip_address == primary_ip_address:
                                            primary_ip_id = ip_id
                                    else:
                                        nautobot_client.http_call(method="post", url="/api/ipam/ip-address-to-interface/", json_data=mapping_payload)
                                        console.log(f"Applied mapping for IP {ip_address} to interface {iface_result.get('id')} on device {device_name}", style="success")
                                        if primary_ip_address and ip_address == primary_ip_address:
                                            primary_ip_id = ip_id
                                except Exception as e:
                                    console.log(f"Error applying mapping for IP {ip_address}: {e}", style="error")
                                continue
                            ns_name = ip_obj.get("namespace")
                            ns_id = namespaces_lookup.get(ns_name)
                            if not ns_id:
                                console.log(f"Namespace '{ns_name}' not found; skipping ip-address {ip_address}.", style="error")
                                continue
                            ip_type = ip_obj.get("type").lower() if ip_obj.get("type") else None
                            ip_status_id = statuses_lookup.get(ip_obj.get("status"))
                            if not ip_status_id:
                                console.log(f"Status '{ip_obj.get('status')}' not found; skipping ip-address {ip_address}.", style="error")
                                continue
                            ip_payload = {
                                "address": ip_address,
                                "namespace": {"id": ns_id},
                                "type": ip_type,
                                "status": {"id": ip_status_id},
                            }
                            try:
                                ip_result = nautobot_client.http_call(method="post", url="/api/ipam/ip-addresses/", json_data=ip_payload)
                                ip_id = ip_result.get("id")
                                if not ip_id:
                                    console.log(f"Failed to create IP Address for {ip_address}", style="error")
                                    continue
                                console.log(f"Created IP Address {ip_address}", style="success")
                                mapping_payload = {"ip_address": {"id": ip_id}, "interface": {"id": iface_result.get("id")}}
                                nautobot_client.http_call(method="post", url="/api/ipam/ip-address-to-interface/", json_data=mapping_payload)
                                console.log(f"Applied IP address {ip_address} to interface {iface_result.get('id')} on device {device_name}", style="success")
                                if primary_ip_address and ip_address == primary_ip_address:
                                    primary_ip_id = ip_id
                            except Exception as e:
                                console.log(f"Error creating IP address mapping for {ip_address}: {e}", style="error")
                if primary_ip_address and primary_ip_id:
                    # Only update if the current primary IP does not match the desired one.
                    current_primary = None
                    if device_name in existing_devices:
                        # Assuming the device's primary_ip4 field is a dict with an "id" key.
                        current_primary = existing_devices[device_name].get("primary_ip4", {}).get("id")
                    # If the current primary IP is different from what we want, update it.
                    if current_primary != primary_ip_id:
                        try:
                            patch_payload = {"primary_ip4": {"id": primary_ip_id}}
                            device_id_to_patch = existing_devices[device_name].get("id") if device_name in existing_devices else result.get("id")
                            _ = nautobot_client.http_call(method="patch", url=f"/api/dcim/devices/{device_id_to_patch}/", json_data=patch_payload)
                            console.log(f"Updated Device: {device_name} with primary IP {primary_ip_address}", style="success")
                        except Exception as e:
                            console.log(f"Error updating primary IP for device '{device_name}': {e}", style="error")

        console.log("Sync process completed.", style="warning")

# -------------------------------
# New: Process Interface Templates
# -------------------------------
def process_interface_templates(nautobot_client: NautobotClient, repo_dir: str, filename: str, device_types_lookup: dict):
    """
    Process interface templates from a YAML file with the following format:
    
    - Test 123:
        - name: test0
          type: virtual
          mgmt_only: true
        - name: test1
          type: virtual

    The key is the device type name. For each interface template, we check via a GET call
    if a template with the same name exists for the given device type. If it exists, we do nothing.
    """
    import os, yaml
    file_path = os.path.join(repo_dir, filename)
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        console.log(f"{filename} not found or empty; skipping interface templates.", style="warning")
        return
    try:
        with open(file_path, "r") as f:
            data_list = yaml.safe_load(f)
    except Exception as e:
        console.log(f"Error reading {filename}: {e}", style="error")
        return
    if not isinstance(data_list, list):
        console.log(f"{filename} does not contain a list; skipping interface templates.", style="warning")
        return
    console.log(f"Processing interface templates from {filename}.", style="info")
    for entry in data_list:
        # Each entry should be a dict with exactly one key: the device type name.
        if not isinstance(entry, dict) or len(entry) != 1:
            console.log("Invalid interface template entry format; skipping.", style="warning")
            continue
        device_type_name, templates = list(entry.items())[0]
        device_type_id = device_types_lookup.get(device_type_name)
        if not device_type_id:
            console.log(f"Device type '{device_type_name}' not found; skipping interface templates for this device type.", style="error")
            continue
        if not isinstance(templates, list):
            console.log(f"Interface templates for device type '{device_type_name}' are not in list format; skipping.", style="warning")
            continue
        for template in templates:
            template_name = template.get("name")
            if not template_name:
                console.log("Interface template missing name; skipping.", style="warning")
                continue
            # Use query parameter 'device_type' to check for existing templates.
            get_url = f"/api/dcim/interface-templates/?device_type={device_type_id}&name={template_name}"
            try:
                resp = nautobot_client.http_call(method="get", url=get_url)
                results = resp.get("results", [])
            except Exception as e:
                console.log(f"Error retrieving interface template '{template_name}': {e}", style="error")
                results = []
            if results:
                continue
            payload = {
                "name": template_name,
                "type": template.get("type").lower() if template.get("type") else None,
                "mgmt_only": template.get("mgmt_only", False),
                "device_type": {"id": device_type_id}
            }
            try:
                result = nautobot_client.http_call(method="post", url="/api/dcim/interface-templates/", json_data=payload)
                console.log(f"Created Interface: {result.get('display') or template_name} for device type '{device_type_name}'", style="success")
            except Exception as e:
                console.log(f"Error creating interface template '{template_name}': {e}", style="error")



# -------------------------------
# End of deploy functions
# -------------------------------


