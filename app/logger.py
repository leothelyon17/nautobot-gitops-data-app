# logger.py
import streamlit as st

class Console:
    def log(self, message: str, style: str = None):
        if style == "error":
            st.error(message)
        elif style == "warning":
            st.warning(message)
        elif style in ("success", "imported"):
            st.success(message)
        else:
            st.info(message)

console = Console()

