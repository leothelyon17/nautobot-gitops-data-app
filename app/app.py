import streamlit as st
from streamlit_extras.stylable_container import stylable_container
from sync import check_and_compare_objects  # Assuming sync.py contains check/compare functions.
from deploy import sync_all_objects_from_git
from delete import delete_all_data

st.title("NautobotCD GitOps Tool")

st.markdown(
    """
Provide your Nautobot credentials, a Git repository URL (ending with `.git`), and the relative directory path within that repository 
where your Nautobot YAML object files are located.

- **Sync with Git:** Verify the presence of required YAML files and compare the objects with those already in Nautobot.
- **Deploy to Nautobot:** Import all objects in dependency order:
    1. Independent objects: Roles, Manufacturers, Location Types, Statuses, Prefixes.
    2. Dependent objects: Device Types (dependent on Manufacturers), Locations (dependent on Location Types), then Devices (dependent on Role, Status, Location, and Device Type; may include interfaces with optional mgmt_only, IP addresses with assignment as primary IP).
- **Delete All Data:** Permanently delete all objects from Nautobot in the following order:
    Devices → IP Addresses → Prefixes → Device Types & Locations → Roles, Manufacturers, Location Types, Statuses.
"""
)

nautobot_token = st.text_input("Enter Nautobot Token")
nautobot_url = st.text_input("Enter Nautobot URL", value="http://localhost:8080")
git_repo_url = st.text_input("Enter Git Repository URL (ending with .git)")

# --- New: Checkbox for Git authentication ---
need_auth = st.checkbox("Need Authentication? Check here.")
if need_auth:
    git_username = st.text_input("Git Username")
    git_pat = st.text_input("Git Personal Access Token", type="password")
else:
    git_username = None
    git_pat = None

subdirectory = st.text_input("Enter directory path within the repo (e.g., 'nautobot/objects')")

if st.button("Sync with Git"):
    if not nautobot_token:
        st.error("Please enter your Nautobot Token.")
    elif not git_repo_url:
        st.error("Please enter the Git repository URL.")
    elif not subdirectory:
        st.error("Please enter the directory path.")
    else:
        st.info("Checking repository for required YAML files and comparing objects...")
        check_and_compare_objects(nautobot_token, git_repo_url, subdirectory, nautobot_url, username=git_username, token=git_pat)

if st.session_state.get("check_done", False):
    with stylable_container("green", css_styles="""
        button {
            background-color: #00FF00;
            color: black;
            font-weight: bold;
        }
    """):
        if st.button("Deploy to Nautobot"):
            if not nautobot_token:
                st.error("Please enter your Nautobot Token.")
            elif not git_repo_url:
                st.error("Please enter the Git repository URL.")
            elif not subdirectory:
                st.error("Please enter the directory path containing your YAML files.")
            else:
                st.info("Starting sync of all objects to Nautobot in dependency order...")
                try:
                    sync_all_objects_from_git(nautobot_token, git_repo_url, subdirectory, nautobot_url, username=git_username, token=git_pat)
                    st.markdown('<div style="background-color: yellow; padding: 5px;">Nautobot data sync process completed (check logs above).</div>', unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"An error occurred during sync: {e}")
else:
    st.info("Please run 'Sync with Git' first to enable deployment.")

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



