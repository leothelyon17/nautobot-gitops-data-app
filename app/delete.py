from nautobot_client import NautobotClient
from logger import console

def delete_all_data(nautobot_token: str, nautobot_url: str = "http://localhost:8080"):
    nautobot_client = NautobotClient(url=nautobot_url, token=nautobot_token)
    deletion_order = [
        {"endpoint": "/api/dcim/devices/", "object_type": "Devices"},
        {"endpoint": "/api/ipam/ip-addresses/", "object_type": "IP Addresses"},
        {"endpoint": "/api/ipam/prefixes/", "object_type": "Prefixes"},
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
            name = obj.get("name") or obj.get("model") or obj.get("prefix") or obj.get("host")
            obj_id = obj.get("id")
            if obj_id:
                delete_url = f"{ep}{obj_id}/"
                try:
                    nautobot_client.http_call(method="delete", url=delete_url)
                    label = "IP Address" if obj_type == "IP Addresses" else ("Prefix" if obj_type == "Prefixes" else obj_type)
                    console.log(f"Deleted {label}: {name}", style="success")
                except Exception as e:
                    console.log(f"Error deleting {obj_type if obj_type != 'Prefixes' else 'Prefix'} '{name}': {e}", style="error")
    console.log("Deletion process completed.", style="warning")

