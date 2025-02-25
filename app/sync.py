# sync.py
import os
import tempfile
import git
import yaml
import streamlit as st
from nautobot_client import NautobotClient
from logger import console

def check_and_compare_objects(nautobot_token: str, git_repo_url: str, subdirectory: str,
                              nautobot_url: str = "http://localhost:8080"):
    required_files = {
        "manufacturers.yml": {"endpoint": "/api/dcim/manufacturers/?limit=0", "object_type": "Manufacturers", "compare_key": "name"},
        "device_types.yml": {"endpoint": "/api/dcim/device-types/?limit=0", "object_type": "Device Types", "compare_key": "model"},
        "roles.yml": {"endpoint": "/api/extras/roles/?limit=0", "object_type": "Roles", "compare_key": "name"},
        "locations.yml": {"endpoint": "/api/dcim/locations/?limit=0", "object_type": "Locations", "compare_key": "name"},
        "location_types.yml": {"endpoint": "/api/dcim/location-types/?limit=0", "object_type": "Location Types", "compare_key": "name"},
        "statuses.yml": {"endpoint": "/api/extras/statuses/?limit=0", "object_type": "Statuses", "compare_key": "name"},
        "prefixes.yml": {"endpoint": "/api/ipam/prefixes/?limit=0", "object_type": "Prefixes", "compare_key": "prefix"},
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


